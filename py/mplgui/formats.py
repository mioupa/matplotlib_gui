"""保存形式の表と保存ファイル名（runner と codegen が共有する。js / pyodide には依存しない）。"""
from __future__ import annotations

import math
import re

from .errors import UserError

# 保存形式 → (savefig の format, MIME, 拡張子)
FORMATS = {
    "png": ("png", "image/png", "png"),
    "jpg": ("jpeg", "image/jpeg", "jpg"),
    "svg": ("svg", "image/svg+xml", "svg"),
    "pdf": ("pdf", "application/pdf", "pdf"),
}

DEFAULT_SAVE_DPI = 300  # 保存時の解像度の既定値（実際の値は設定 save.dpi。GUI の「保存」と生成コードで共通）

# PNG / JPG の画素数の上限（Pyodide のメモリを守る。計測のうえ、必要なら見直す）
MAX_RASTER_PIXELS = 100_000_000
MAX_RASTER_SIDE = 65536  # 1辺の画素数はこれ未満

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


def savefig_kwargs(file_format: str, transparent: bool = False, dpi: int = DEFAULT_SAVE_DPI) -> dict:
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


def savefig_rc(file_format: str, svg_text: str = "path") -> dict:
    """保存形式ごとの rcParams（runner が savefig の間だけ適用し、生成コードも同じ値を書く）。

    - pdf: 文字を TrueType（Type 42）として埋め込む（Illustrator などで文字を編集できる）。
    - svg: "path" は文字を図形にする。"text"（none）は文字をテキストのまま残す。
    """
    if file_format == "pdf":
        return {"pdf.fonttype": 42}
    if file_format == "svg":
        return {"svg.fonttype": "path" if svg_text == "path" else "none"}
    return {}


def raster_pixels(width_in: float, height_in: float, dpi: float) -> tuple[int, int]:
    return math.ceil(width_in * dpi), math.ceil(height_in * dpi)


def check_raster_size(width_in: float, height_in: float, dpi: float) -> None:
    """PNG / JPG の画素数が大きすぎるときは UserError にする（ベクター形式には使わない）。"""
    width_px, height_px = raster_pixels(width_in, height_in, dpi)
    if width_px * height_px > MAX_RASTER_PIXELS or max(width_px, height_px) >= MAX_RASTER_SIDE:
        raise UserError(
            f"保存する画像が大きすぎます（幅 {width_px} × 高さ {height_px} ピクセル）。保存 DPI か図のサイズを小さくしてください。",
            field="保存 DPI",
        )
