"""ファイルのバイト列から DataFrame を作る（DOM / js には依存しない）。"""
import io
from pathlib import Path

import pandas as pd

SUPPORTED = {".xlsx", ".csv", ".txt"}


def decode_delimiter(delimiter: str, suffix: str) -> str:
    if delimiter:
        return bytes(delimiter, "utf-8").decode("unicode_escape")
    if suffix == ".csv":
        return ","
    return r"\s+"


def load_dataframe(
    file_bytes: bytes,
    filename: str,
    delimiter: str,
    has_header: bool,
) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError("対応していない拡張子です。xlsx/csv/txtを選択してください。")

    header = 0 if has_header else None
    stream = io.BytesIO(file_bytes)

    if suffix == ".xlsx":
        df = pd.read_excel(stream, header=header)
    else:
        sep = decode_delimiter(delimiter, suffix)
        # UTF-8 で読めなければ Shift-JIS にフォールバック
        for enc in ("utf-8", "shift_jis"):
            try:
                stream.seek(0)
                df = pd.read_csv(
                    stream, sep=sep, header=header,
                    engine="python", encoding=enc,
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                if enc == "shift_jis":
                    raise
                continue

    if df.empty:
        raise ValueError("データが空です。")

    if not has_header:
        df.columns = [f"column_{i}" for i in range(len(df.columns))]

    return df
