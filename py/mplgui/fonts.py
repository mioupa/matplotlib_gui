"""日本語フォントの設定と登録（js / pyodide には依存しない。取得処理は JS 側）。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

SANS_SERIF_PRIORITY = [
    "Noto Sans JP",
    "Noto Sans CJK JP",
    "IPAexGothic",
    "Yu Gothic",
    "Hiragino Sans",
    "MS Gothic",
    "DejaVu Sans",
]
PREFERRED_JP_FONTS = ["Noto Sans CJK JP", "Noto Sans JP"]

_registered = False


def configure_rcparams() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = list(SANS_SERIF_PRIORITY)
    plt.rcParams["axes.unicode_minus"] = False


def register_font_file(path) -> None:
    """フォントファイルを matplotlib に登録し、日本語フォントを sans-serif の先頭へ移す。"""
    font_manager.fontManager.addfont(str(path))
    current = list(plt.rcParams.get("font.sans-serif", []))
    for name in reversed(PREFERRED_JP_FONTS):
        if name in current:
            current.remove(name)
        current.insert(0, name)
    plt.rcParams["font.sans-serif"] = current


def register_font_bytes(data: bytes, filename: str = "NotoSansCJKjp-Regular.otf") -> bool:
    """フォントのバイト列を登録する。登録は1セッション1回だけ（2回目以降は何もしない）。"""
    global _registered
    if _registered:
        return False
    target = Path(tempfile.gettempdir()) / filename
    target.write_bytes(bytes(data))
    register_font_file(target)
    _registered = True
    return True


def is_registered() -> bool:
    return _registered
