"""ファイルのバイト列から DataFrame を作り、列の選択肢とプレビューを返す（DOM / js には依存しない）。"""
from __future__ import annotations

import io
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
        return bytes(delimiter, "utf-8").decode("unicode_escape")
    if suffix == ".csv":
        return ","
    return r"\s+"


def load_file(file_bytes: bytes, filename: str, delimiter: str, has_header: bool) -> LoadedData:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise UserError("対応していない拡張子です。xlsx/csv/txtを選択してください。", field="入力ファイル")

    header = 0 if has_header else None
    stream = io.BytesIO(file_bytes)
    used_encoding: str | None = None

    try:
        if suffix == ".xlsx":
            df = pd.read_excel(stream, header=header)
        else:
            sep = decode_delimiter(delimiter, suffix)
            # UTF-8 で読めなければ Shift-JIS にフォールバック（A5 で見直す）
            df = None
            for enc in ("utf-8", "shift_jis"):
                try:
                    stream.seek(0)
                    df = pd.read_csv(stream, sep=sep, header=header, engine="python", encoding=enc)
                    used_encoding = enc
                    break
                except UnicodeDecodeError:
                    if enc == "shift_jis":
                        raise UserError(
                            "文字コードを判定できませんでした。UTF-8 または Shift-JIS で保存し直してください。",
                            field="入力ファイル",
                        )
                    continue
    except UserError:
        raise
    except pd.errors.ParserError as exc:
        raise UserError(
            "ファイルを表として読み込めませんでした。区切り文字や行の形式を確認してください。",
            field="区切り文字",
            detail=str(exc),
        ) from exc
    except pd.errors.EmptyDataError as exc:
        raise UserError("データが空です。", field="入力ファイル") from exc

    if df.empty:
        raise UserError("データが空です。", field="入力ファイル")

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
