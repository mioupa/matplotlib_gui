"""日本語フォントの設定と登録（js / pyodide には依存しない。取得処理は JS 側）。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

# 日本語フォントの優先順（唯一の定義）。codegen が生成するスクリプトの rcParams もこの並びを使う。
SANS_SERIF_PRIORITY = [
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "IPAexGothic",
    "Yu Gothic",
    "Hiragino Sans",
    "MS Gothic",
    "DejaVu Sans",
]

_registered = False


def configure_rcparams() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = list(SANS_SERIF_PRIORITY)
    plt.rcParams["axes.unicode_minus"] = False


def register_font_file(path) -> None:
    """フォントファイルを matplotlib に登録する。rcParams は生成コードと同じ SANS_SERIF_PRIORITY の並びにする。"""
    font_manager.fontManager.addfont(str(path))
    configure_rcparams()


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
