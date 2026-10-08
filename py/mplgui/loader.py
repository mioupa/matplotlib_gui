"""ファイルのバイト列から DataFrame を作り、列の選択肢とプレビューを返す（DOM / js には依存しない）。"""
from __future__ import annotations

import csv
import dataclasses
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
    datetime_columns: tuple["DatetimeColumn", ...] = ()  # 読込のあとで日時に変換した列（生成コードの読込部に変換の行を書く）
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


@dataclass(frozen=True)
class DatetimeColumn:
    """自動で日時と認識した文字列の列。変換の式は convert_datetime（loader）と codegen が同じ内容で持つ。"""

    index: int  # 列番号
    name: str  # 列名（コメント・警告用）
    format: str  # pd.to_datetime の format
    strip: bool = False  # 値に前後の空白があるので .str.strip() してから変換する
    utc: bool = False  # タイムゾーンが混在しているので utc=True で UTC にそろえる
    has_tz: bool = False  # format に %z を含む（変換後に .dt.tz_localize(None) で書かれた時刻にする）


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


# ---------------------------------------------------------------- datetime recognition (D5)

_DATE_PARTS = ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日")  # 年が先頭のものだけ（月日の順が曖昧な 01/02/2024 は認識しない）
_TIME_PARTS = ("", " %H:%M", " %H:%M:%S", " %H:%M:%S.%f")
_ISO_TIME_PARTS = ("T%H:%M", "T%H:%M:%S", "T%H:%M:%S.%f")


def _candidate_formats() -> tuple[str, ...]:
    out: list[str] = []
    for date in _DATE_PARTS:
        out.extend(date + t for t in _TIME_PARTS)
        if date == "%Y-%m-%d":
            out.extend(date + t for t in _ISO_TIME_PARTS)
            # 時刻のあるもの（スペース区切り・T 区切り）は、末尾にタイムゾーン（Z / +09:00）が付いた書式も候補にする
            out.extend(date + t + "%z" for t in _TIME_PARTS[1:] + _ISO_TIME_PARTS)
    return tuple(out)


DATETIME_FORMATS = _candidate_formats()
DATETIME_SAMPLE = 100  # 先頭から、すべてが読めなければならない値の数
DATETIME_MIN_RATIO = 0.9  # 空欄以外のうち、読めなければならない割合
_OFFSET = re.compile(r"(Z|[+-]\d{2}(?::?\d{2})?)$")


def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""


def _offset_of(text: str) -> str:
    m = _OFFSET.search(text)
    if not m:
        return ""
    o = m.group(1).replace(":", "")
    if o == "Z":
        return "+0000"
    return o if len(o) == 5 else o + "00"


def _parses(values: list[str], fmt: str) -> int:
    """fmt で読める値の数（%z の書式は、オフセットが混在していても読めるものとして数える）。"""
    kwargs = {"utc": True} if "%z" in fmt else {}
    try:
        return int(pd.to_datetime(pd.Series(values, dtype=object), format=fmt, errors="coerce", **kwargs).notna().sum())
    except (ValueError, TypeError, OverflowError):
        return 0


def _detect_one(index: int, name, column: pd.Series) -> DatetimeColumn | None:
    if not (pd.api.types.is_object_dtype(column.dtype) or pd.api.types.is_string_dtype(column.dtype)):
        return None
    raw = [v for v in column.tolist() if not _is_blank(v)]
    if not raw or any(not isinstance(v, str) for v in raw):
        return None
    texts = [v.strip() for v in raw]
    numeric = pd.to_numeric(pd.Series(texts, dtype=object), errors="coerce").notna().sum()
    if numeric * 2 >= len(texts):
        return None
    sample = texts[:DATETIME_SAMPLE]
    for fmt in DATETIME_FORMATS:
        if _parses(sample, fmt) != len(sample):
            continue
        if _parses(texts, fmt) < DATETIME_MIN_RATIO * len(texts):
            continue
        has_tz = "%z" in fmt
        utc = has_tz and len({_offset_of(t) for t in texts if _OFFSET.search(t)}) > 1
        strip = any(v != v.strip() for v in raw)
        return DatetimeColumn(index=index, name=str(name), format=fmt, strip=strip, utc=utc, has_tz=has_tz)
    return None


def detect_datetime_columns(df: pd.DataFrame) -> tuple[DatetimeColumn, ...]:
    """日時として読める文字列の列を探す（df は変更しない）。採用条件は、前後の空白を除いた先頭 100 個の
    空欄以外の値がすべて読め、かつ空欄以外の 90% 以上が読めること。数値の列（半数以上が数値）は除く。"""
    found = []
    for i in range(df.shape[1]):
        spec = _detect_one(i, df.columns[i], df.iloc[:, i])
        if spec is not None:
            found.append(spec)
    return tuple(found)


def convert_datetime(series: pd.Series, spec: DatetimeColumn) -> pd.Series:
    """列を日時に変換する。生成コードの `df.isetitem(i, pd.to_datetime(...))` の式と同じ内容（codegen が文字列にする）。"""
    source = series.str.strip() if spec.strip else series
    kwargs = {"utc": True} if spec.utc else {}
    out = pd.to_datetime(source, format=spec.format, errors="coerce", **kwargs)
    return out.dt.tz_localize(None) if spec.has_tz else out


def apply_datetime_columns(df: pd.DataFrame, specs: tuple[DatetimeColumn, ...]) -> list[str]:
    """df の列を（その場で）日時に変換し、警告の文を返す（読めない値は NaT になる）。"""
    warnings_out: list[str] = []
    for spec in specs:
        original = df.iloc[:, spec.index]
        converted = convert_datetime(original, spec)
        df.isetitem(spec.index, converted)
        where = f"列「{spec.name}」[{spec.index}]"
        if spec.utc:
            warnings_out.append(f"{where}: タイムゾーンの異なる日時が混在しているため、UTC の時刻にそろえました。")
        failed = [str(v).strip() for v, ok in zip(original.tolist(), converted.notna().tolist()) if not ok and not _is_blank(v)]
        if failed:
            examples: list[str] = []
            for text in failed:
                if text not in examples:
                    examples.append(text)
                if len(examples) >= 3:
                    break
            ex = ", ".join(f'"{e}"' for e in examples)
            warnings_out.append(f"{where}: 日時として読めない値が{len(failed)}件あったため、欠損として扱います（例: {ex}）。")
    return warnings_out


def column_kind(dtype) -> str:
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"
    if pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_bool_dtype(dtype):
        return "number"
    return "text"


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
    parse_dates: bool = True,
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

    # 日時の列の認識（Excel の日付セルは、もともと datetime64 なので対象外で、設定に関係なく日時）
    datetime_columns = detect_datetime_columns(df) if parse_dates else ()
    warnings_out.extend(apply_datetime_columns(df, datetime_columns))

    return LoadedData(
        df=df,
        encoding=used_encoding,
        source=dataclasses.replace(make_source(), datetime_columns=datetime_columns),
        warnings=warnings_out,
        preamble_lines=preamble,
        preamble_total=skip_lines if preamble else 0,
    )


def load_dataframe(file_bytes: bytes, filename: str, delimiter: str, has_header: bool) -> pd.DataFrame:
    return load_file(file_bytes, filename, delimiter, has_header).df


def column_options(df: pd.DataFrame) -> list[dict]:
    """列セレクト用の選択肢。値は列番号ベース（"__idx__N"）で、同名列も区別できる。"""
    return [
        {"value": f"__idx__{i}", "label": f"{col} [{i}]", "kind": column_kind(df.dtypes.iloc[i])}
        for i, col in enumerate(df.columns)
    ]


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
        "columnKinds": [column_kind(dt) for dt in df.dtypes],
        "rows": _format_cells(preview_df),
        "totalRows": int(len(df)),
        "totalColumns": int(len(df.columns)),
        "limit": limit,
        "truncated": bool(len(df) > limit),
    }
