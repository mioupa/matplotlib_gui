"""日本語フォントの設定と登録（js / pyodide には依存しない。取得処理は JS 側）。"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

# 日本語フォントの優先順（唯一の定義）。codegen が生成するスクリプトの rcParams もこの並びを使う。
SANS_SERIF_PRIORITY = [
    "Noto Sans JP",
    "Noto Sans CJK JP",
    "IPAexGothic",
    "Yu Gothic",
    "Hiragino Sans",
    "MS Gothic",
    "DejaVu Sans",
]


@dataclass(frozen=True)
class LatinFont:
    display: str
    candidates: tuple[str, ...]  # 先頭から、入っているものを使う
    mathtext_fontset: str | None = None


# 欧文フォントの表（唯一の定義）。codegen が生成するスクリプトもこれを使う。
LATIN_FONTS = {
    "arimo": LatinFont("Arimo（Arial 互換）", ("Arimo", "Arial", "Liberation Sans")),
    "tinos": LatinFont("Tinos（Times 互換）", ("Tinos", "Times New Roman", "Liberation Serif"), "stix"),
}

# 登録するフォントの種類 → 作業ファイル名
FONT_FILENAMES = {
    "japanese": "NotoSansJP-Regular.ttf",
    "arimo": "Arimo-Regular.ttf",
    "tinos": "Tinos-Regular.ttf",
}

_registered: set[str] = set()


def configure_rcparams() -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = list(SANS_SERIF_PRIORITY)
    plt.rcParams["axes.unicode_minus"] = False


def register_font_file(path) -> None:
    """フォントファイルを matplotlib に登録する。rcParams は生成コードと同じ SANS_SERIF_PRIORITY の並びにする。"""
    font_manager.fontManager.addfont(str(path))
    configure_rcparams()


def register_font_bytes(data: bytes, filename: str | None = None, kind: str = "japanese") -> bool:
    """フォントのバイト列を登録する。登録は種類ごとに1セッション1回だけ（2回目以降は何もせず False）。

    kind は "japanese" | "arimo" | "tinos"。日本語は rcParams も生成コードと同じ並びにする。
    """
    if kind not in FONT_FILENAMES:
        raise ValueError(f"未対応のフォントの種類です: {kind}")
    if kind in _registered:
        return False
    target = Path(tempfile.gettempdir()) / (filename or FONT_FILENAMES[kind])
    target.write_bytes(bytes(data))
    if kind == "japanese":
        register_font_file(target)
    else:
        font_manager.fontManager.addfont(str(target))
    _registered.add(kind)
    return True


def is_registered(kind: str = "japanese") -> bool:
    return kind in _registered


def registered_kinds() -> list[str]:
    return sorted(_registered)
