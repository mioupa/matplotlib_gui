"""ファイルのバイト列から DataFrame を作り、列の選択肢とプレビューを返す（DOM / js には依存しない）。"""
from __future__ import annotations

import csv
import io
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .errors import UserError

SUPPORTED = {".xlsx", ".csv", ".txt", ".tsv"}
PREVIEW_ROWS = 100
PREAMBLE_LINES = 20  # 前置き行として画面に出す最大の行数


@dataclass(frozen=True)
class SourceInfo:
    """読み込んだファイルの情報。codegen が生成スクリプトの「データの読み込み」部に使う。"""

    filename: str
    kind: str  # "csv" | "txt" | "tsv" | "xlsx"
    encoding: str | None = None  # xlsx は None
    separator: str | None = None  # デコード後の区切り文字（csv / txt）。xlsx は None
    has_header: bool = True
    sheet_name: str | None = None  # xlsx のみ（読んだシート）
    skip_lines: int = 0  # ヘッダより前に読み飛ばす行数
    thousands: str | None = None  # None = なし
    decimal: str = "."
    comment: str | None = None  # None = なし
    sheets: tuple[str, ...] = ()  # xlsx のシート一覧
    datetime_columns: tuple = ()  # D5 用（未使用）
    pasted: bool = False  # 貼り付けたデータ（pasted_data.tsv）。生成コードに保存の案内を書く

    def read_kwargs(self) -> dict:
        """pd.read_csv / pd.read_excel に渡す引数（文字コードとファイルを除く）。順序は生成スクリプトの並びと同じ。

        loader と codegen が同じ定義を使う（読み方が食い違わないようにする）。
        """
        common = {
            "header": 0 if self.has_header else None,
            "skiprows": self.skip_lines,
            "thousands": self.thousands,
            "decimal": self.decimal,
            "comment": self.comment,
        }
        if self.kind == "xlsx":
            return {"sheet_name": self.sheet_name, **common}
        return {"sep": self.separator, **common, "engine": "python"}


@dataclass
class LoadedData:
    df: pd.DataFrame
    encoding: str | None  # xlsx は None
    source: SourceInfo | None = None
    warnings: list[str] = field(default_factory=list)  # 読込時の警告（画面の警告に出す）
    preamble_lines: tuple[str, ...] = ()  # 読み飛ばした行（最大 PREAMBLE_LINES 行）
    preamble_total: int = 0  # 読み飛ばした行数


# バックスロッシュ表記（\t, \x41, \u3001 など）だけを解釈する。それ以外（「、」などの非 ASCII 文字）は変更しない。
_ESCAPE = re.compile(r"\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[0-7]{1,3}|.)", re.DOTALL)


def _decode_escapes(text: str) -> str:
    def repl(match: re.Match) -> str:
        token = match.group(0)
        if not token.isascii():
            return token
        with warnings.catch_warnings():
            # 「\d」のような未定義のエスケープは、文字のまま残る（"\\d"）が DeprecationWarning が出る。これだけを無視する
            warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*invalid escape sequence")
            return token.encode("ascii").decode("unicode_escape")

    return _ESCAPE.sub(repl, text)


def decode_delimiter(delimiter: str, suffix: str) -> str:
    if delimiter:
        try:
            return _decode_escapes(delimiter)
        except UnicodeDecodeError as exc:
            raise UserError(
                "「区切り文字」のエスケープ表記が正しくありません。\\t（タブ）のように書くか、記号をそのまま入力してください。",
                field="区切り文字",
                detail=str(exc),
            ) from exc
    if suffix == ".csv":
        return ","
    if suffix == ".tsv":
        return "\t"
    return r"\s+"


_BOM_UTF8 = b"\xef\xbb\xbf"


# Python の cp932 は未定義の単一バイト（0x80, 0xA0, 0xFD-0xFF）を C1 制御文字・私用領域 U+F8F0-F8F3 に
# 「デコードできてしまう」。これらを含む候補は文字コードの誤りとみなして除外する。
_IMPLAUSIBLE = re.compile("[\u0080-\u009f\uf8f0-\uf8f3\ufffd]")


def _suspicion(text: str) -> int:
    """文字化けらしさ。半角カナ・私用領域・置換文字・制御文字の数（少ないほど自然な日本語）。"""
    n = 0
    for ch in text:
        o = ord(ch)
        if 0xFF61 <= o <= 0xFF9F or 0xE000 <= o <= 0xF8FF or o == 0xFFFD:
            n += 1
        elif o < 0x20 and ch not in "\t\r\n":
            n += 1
        elif 0x7F <= o <= 0x9F:
            n += 1
    return n


def detect_encoding(data: bytes) -> tuple[str, str]:
    """バイト列から文字コードを決め、(コード, デコード済みテキスト) を返す。

    順序: BOM 付き UTF-8 → UTF-8 → CP932 / EUC-JP。
    CP932 と EUC-JP の両方で厳密にデコードできる場合は、半角カナ等の「文字化けらしい文字」が
    少ないほうを採用し、同数なら CP932 を優先する。
    """
    if data.startswith(_BOM_UTF8):
        try:
            return "utf-8-sig", data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass  # BOM の後ろが UTF-8 でない場合は他の候補へ
    else:
        try:
            return "utf-8", data.decode("utf-8")
        except UnicodeDecodeError:
            pass

    candidates = []
    for code in ("cp932", "euc-jp"):  # 同点のときは先に並べたほうが勝つ
        try:
            text = data.decode(code)
        except UnicodeDecodeError:
            continue
        if not _IMPLAUSIBLE.search(text):
            candidates.append((code, text))
    if not candidates:
        raise UserError(
            "文字コードを判定できませんでした（UTF-8 / Shift_JIS(CP932) / EUC-JP のいずれでもありません）。"
            "ファイルを UTF-8 で保存し直してから読み込んでください。",
            field="入力ファイル",
        )
    return min(candidates, key=lambda c: _suspicion(c[1]))  # min は同点で先頭を返す


SKIP_LINES_HINT = "ファイルの先頭に説明の行があるときは、「ヘッダより前に読み飛ばす行数」を指定してください。"
SKIP_LINES_TOO_LARGE_HINT = "「ヘッダより前に読み飛ばす行数」が大きすぎないか確認してください。"
DELIMITER_HINT = "列が1つしか読み込めませんでした。区切り文字（; やタブなど）を「区切り文字」に指定してください。"
_EXCEL_OPEN_ERROR = (
    "Excelファイル（.xlsx）を読み込めませんでした。ファイルが壊れていないか、パスワードが掛かっていないかを確認し、"
    "Excelで開いて .xlsx で保存し直してください。"
)


def open_excel(file_bytes: bytes) -> pd.ExcelFile:
    """xlsx を開く（シートの切り替えで開き直さないように、呼び出し側が保持する）。"""
    try:
        return pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as exc:
        raise UserError(_EXCEL_OPEN_ERROR, field="入力ファイル", detail=f"{type(exc).__name__}: {exc}") from exc


def _check_conflicts(sep: str, thousands: str, comment: str) -> None:
    if thousands == " " and sep == r"\s+":
        raise UserError("区切り文字が空白のときは、桁区切りに空白は使えません。", field="桁区切り")
    if comment and comment == sep:
        raise UserError("「コメント記号」に、区切り文字と同じ記号は使えません。", field="コメント記号")


def _first_data_line(text: str, skip_lines: int, comment: str) -> str:
    for line in text.splitlines()[skip_lines:]:
        if line.strip() and not (comment and line.lstrip().startswith(comment)):
            return line
    return ""


def _delimiter_warning(text: str, sep: str, skip_lines: int, comment: str) -> str | None:
    """1 列しか読めなかったとき、先頭のデータ行に ; かタブがあれば、区切り文字の指定漏れとして案内する。"""
    line = _first_data_line(text, skip_lines, comment)
    for candidate in (";", "\t"):
        if candidate in line and sep != candidate:
            return DELIMITER_HINT
    return None


def _excel_preamble(excel: pd.ExcelFile, sheet: str, skip_lines: int) -> tuple[str, ...]:
    head = excel.parse(sheet_name=sheet, header=None, nrows=min(skip_lines, PREAMBLE_LINES))
    lines = []
    for row in head.itertuples(index=False, name=None):
        cells = ["" if pd.isna(v) else str(v) for v in row]
        lines.append("\t".join(cells).rstrip("\t"))
    return tuple(lines)


def load_file(
    file_bytes: bytes,
    filename: str,
    delimiter: str = "",
    has_header: bool = True,
    *,
    skip_lines: int = 0,
    thousands: str = "",
    decimal: str = ".",
    comment: str = "",
    sheet: str = "",
    excel: pd.ExcelFile | None = None,
) -> LoadedData:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise UserError("対応していない拡張子です。xlsx/csv/txt/tsvを選択してください。", field="入力ファイル")

    used_encoding: str | None = None
    sep: str | None = None
    sheet_name: str | None = None
    sheets: tuple[str, ...] = ()
    text = ""
    warnings_out: list[str] = []
    preamble: tuple[str, ...] = ()

    def make_source() -> SourceInfo:
        return SourceInfo(
            filename=Path(filename).name,
            kind=suffix.lstrip("."),
            encoding=used_encoding,
            separator=sep,
            has_header=has_header,
            sheet_name=sheet_name,
            skip_lines=skip_lines,
            thousands=thousands or None,
            decimal=decimal,
            comment=comment or None,
            sheets=sheets,
        )

    try:
        if suffix == ".xlsx":
            if excel is None:
                excel = open_excel(file_bytes)
            sheets = tuple(str(n) for n in excel.sheet_names)
            if sheet == "":
                sheet_name = sheets[0]
            elif sheet in sheets:
                sheet_name = sheet
            else:
                raise UserError(f"シート「{sheet}」がファイルにありません。シートを選び直してください。", field="シート")
            kwargs = make_source().read_kwargs()
            try:
                df = excel.parse(**kwargs)
                if skip_lines > 0 and not df.empty:
                    preamble = _excel_preamble(excel, sheet_name, skip_lines)
            except Exception as exc:
                raise UserError(_EXCEL_OPEN_ERROR, field="入力ファイル", detail=f"{type(exc).__name__}: {exc}") from exc
        else:
            sep = decode_delimiter(delimiter, suffix)
            _check_conflicts(sep, thousands, comment)
            used_encoding, text = detect_encoding(file_bytes)
            kwargs = make_source().read_kwargs()
            df = pd.read_csv(io.StringIO(text), **kwargs)
            if skip_lines > 0:
                preamble = tuple(text.splitlines()[:skip_lines][:PREAMBLE_LINES])
    except UserError:
        raise
    except pd.errors.EmptyDataError as exc:
        message = "ファイルにデータがありません。内容のあるファイルを選択してください。"
        if skip_lines > 0:
            message += SKIP_LINES_TOO_LARGE_HINT
        raise UserError(message, field="入力ファイル") from exc
    except (pd.errors.ParserError, ValueError, re.error, csv.Error) as exc:
        # 列数の不整合、区切り文字が正規表現として不正、など
        raise UserError(
            "ファイルを表として読み込めませんでした。「区切り文字」の設定（正規表現として正しいか）や、"
            "行ごとの列数が揃っているかを確認してください。" + SKIP_LINES_HINT,
            field="区切り文字",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    if df.empty:
        message = "ファイルにデータ行がありません。ヘッダ行だけでなく、データ行を含むファイルを選択してください。"
        if skip_lines > 0:
            message += SKIP_LINES_TOO_LARGE_HINT
        raise UserError(message, field="入力ファイル")

    if not has_header:
        df.columns = [f"column_{i}" for i in range(len(df.columns))]

    if suffix != ".xlsx" and len(df.columns) == 1:
        hint = _delimiter_warning(text, sep, skip_lines, comment)
        if hint:
            warnings_out.append(hint)

    return LoadedData(
        df=df,
        encoding=used_encoding,
        source=make_source(),
        warnings=warnings_out,
        preamble_lines=preamble,
        preamble_total=skip_lines if preamble else 0,
    )


def load_dataframe(file_bytes: bytes, filename: str, delimiter: str, has_header: bool) -> pd.DataFrame:
    return load_file(file_bytes, filename, delimiter, has_header).df


def column_options(df: pd.DataFrame) -> list[dict]:
    """列セレクト用の選択肢。値は列番号ベース（"__idx__N"）で、同名列も区別できる。"""
    return [{"value": f"__idx__{i}", "label": f"{col} [{i}]"} for i, col in enumerate(df.columns)]


def _format_cells(preview_df: pd.DataFrame) -> list[list[str]]:
    """pandas の表示と同じ書式（to_html と同じ桁数・NaN 表記）で文字列にする。"""
    try:
        from pandas.io.formats.format import format_array

        cols = [[s.strip() for s in format_array(preview_df.iloc[:, i]._values, None)] for i in range(preview_df.shape[1])]
        return [list(row) for row in zip(*cols)] if cols else []
    except Exception:
        return [[str(v) for v in row] for row in preview_df.itertuples(index=False, name=None)]


def build_preview(df: pd.DataFrame, limit: int = PREVIEW_ROWS, preamble: tuple[tuple[str, ...], int] | None = None) -> dict:
    """プレビュー。preamble は (読み飛ばした行, 行数)。行数が 0 のとき preview["preamble"] は None。"""
    preview_df = df.head(limit)
    lines, total = preamble if preamble else ((), 0)
    return {
        "preamble": {"lines": list(lines[:PREAMBLE_LINES]), "total": int(total)} if total > 0 else None,
        "columns": [str(c) for c in df.columns],
        "rows": _format_cells(preview_df),
        "totalRows": int(len(df)),
        "totalColumns": int(len(df.columns)),
        "limit": limit,
        "truncated": bool(len(df) > limit),
    }
