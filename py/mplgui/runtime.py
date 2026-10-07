"""実行環境の初期設定（警告フィルタ）。js / pyodide には依存しない。"""
from __future__ import annotations

import warnings

# 無視してよい警告だけを列挙する。DeprecationWarning 全体は無視しない（A10）。
_PYARROW_MESSAGE = r"(?s).*[Pp]yarrow.*"
_MISSING_GLYPH_MESSAGES = (r"Glyph .* missing from font.*", r".*missing from current font.*")


def configure_warnings() -> None:
    """pandas の pyarrow 関連 DeprecationWarning と、matplotlib のグリフ不足 UserWarning だけを無視する。"""
    warnings.filterwarnings("ignore", message=_PYARROW_MESSAGE, category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pyarrow(\..*)?$")
    for message in _MISSING_GLYPH_MESSAGES:
        warnings.filterwarnings("ignore", message=message, category=UserWarning)
