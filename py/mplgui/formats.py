"""保存形式の表と保存ファイル名（runner と codegen が共有する。js / pyodide には依存しない）。"""
from __future__ import annotations

import re

# 保存形式 → (savefig の format, MIME, 拡張子)
FORMATS = {
    "png": ("png", "image/png", "png"),
    "jpg": ("jpeg", "image/jpeg", "jpg"),
    "svg": ("svg", "image/svg+xml", "svg"),
    "pdf": ("pdf", "application/pdf", "pdf"),
}

SAVE_DPI = 120  # 保存時の解像度（GUI の「保存」と生成コードで共通）

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def build_filename(raw_filename: str, ext: str) -> str:
    """保存ファイル名を作る。空欄時は plot.<ext>。入力中の拡張子は取り除いて ext を付ける。"""
    raw_filename = _INVALID_FILENAME_CHARS.sub("_", (raw_filename or "").strip())
    if raw_filename:
        filename_base = raw_filename.rstrip(".")
        if "." in filename_base:
            filename_base = filename_base.rsplit(".", 1)[0]
        filename_base = filename_base.strip() or "plot"
        return f"{filename_base}.{ext}"
    return f"plot.{ext}"


def savefig_kwargs(file_format: str, transparent: bool = False, dpi: int = SAVE_DPI) -> dict:
    """figure.savefig に渡す引数（format 以外）。"""
    save_format = FORMATS[file_format][0]
    kwargs: dict = {}
    if save_format in {"png", "jpeg"}:
        kwargs["dpi"] = dpi
    if save_format == "jpeg":
        kwargs["facecolor"] = "white"
    if transparent:
        kwargs["transparent"] = True
    return kwargs
