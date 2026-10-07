"""ファイルのバイト列から DataFrame を作り、列の選択肢とプレビューを返す（DOM / js には依存しない）。"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .errors import UserError

SUPPORTED = {".xlsx", ".csv", ".txt"}
PREVIEW_ROWS = 100


@dataclass
class LoadedData:
    df: pd.DataFrame
    encoding: str | None  # xlsx は None


def decode_delimiter(delimiter: str, suffix: str) -> str:
    if delimiter:
        try:
            return bytes(delimiter, "utf-8").decode("unicode_escape")
        except UnicodeDecodeError as exc:
            raise UserError(
                "「区切り文字」のエスケープ表記が正しくありません。\\t（タブ）のように書くか、記号をそのまま入力してください。",
                field="区切り文字",
                detail=str(exc),
            ) from exc
    if suffix == ".csv":
        return ","
    return r"\s+"


_BOM_UTF8 = b"\xef\xbb\xbf"


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
            candidates.append((code, data.decode(code)))
        except UnicodeDecodeError:
            continue
    if not candidates:
        raise UserError(
            "文字コードを判定できませんでした（UTF-8 / Shift_JIS(CP932) / EUC-JP のいずれでもありません）。"
            "ファイルを UTF-8 で保存し直してから読み込んでください。",
            field="入力ファイル",
        )
    return min(candidates, key=lambda c: _suspicion(c[1]))  # min は同点で先頭を返す


def load_file(file_bytes: bytes, filename: str, delimiter: str, has_header: bool) -> LoadedData:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise UserError("対応していない拡張子です。xlsx/csv/txtを選択してください。", field="入力ファイル")

    header = 0 if has_header else None
    used_encoding: str | None = None

    try:
        if suffix == ".xlsx":
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), header=header)
            except Exception as exc:
                raise UserError(
                    "Excelファイル（.xlsx）を読み込めませんでした。ファイルが壊れていないか、パスワードが掛かっていないかを確認し、"
                    "Excelで開いて .xlsx で保存し直してください。",
                    field="入力ファイル",
                    detail=f"{type(exc).__name__}: {exc}",
                ) from exc
        else:
            sep = decode_delimiter(delimiter, suffix)
            used_encoding, text = detect_encoding(file_bytes)
            df = pd.read_csv(io.StringIO(text), sep=sep, header=header, engine="python")
    except UserError:
        raise
    except pd.errors.EmptyDataError as exc:
        raise UserError("ファイルにデータがありません。内容のあるファイルを選択してください。", field="入力ファイル") from exc
    except (pd.errors.ParserError, ValueError, re.error, csv.Error) as exc:
        # 列数の不整合、区切り文字が正規表現として不正、など
        raise UserError(
            "ファイルを表として読み込めませんでした。「区切り文字」の設定（正規表現として正しいか）や、"
            "行ごとの列数が揃っているかを確認してください。",
            field="区切り文字",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    if df.empty:
        raise UserError("ファイルにデータ行がありません。ヘッダ行だけでなく、データ行を含むファイルを選択してください。", field="入力ファイル")

    if not has_header:
        df.columns = [f"column_{i}" for i in range(len(df.columns))]

    return LoadedData(df=df, encoding=used_encoding)


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


def build_preview(df: pd.DataFrame, limit: int = PREVIEW_ROWS) -> dict:
    preview_df = df.head(limit)
    return {
        "columns": [str(c) for c in df.columns],
        "rows": _format_cells(preview_df),
        "totalRows": int(len(df)),
        "totalColumns": int(len(df.columns)),
        "limit": limit,
        "truncated": bool(len(df) > limit),
    }
