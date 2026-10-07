import warnings

import pytest

from mplgui.runtime import configure_warnings

pytestmark = pytest.mark.unit


def _emit(category, message):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        configure_warnings()
        warnings.warn(message, category)
    return caught


def test_unrelated_deprecation_warning_is_still_emitted():
    caught = _emit(DeprecationWarning, "something else is deprecated")
    assert [str(w.message) for w in caught] == ["something else is deprecated"]


def test_pyarrow_deprecation_warning_is_ignored():
    assert not _emit(
        DeprecationWarning,
        "\nPyarrow will become a required dependency of pandas in the next major release of pandas",
    )


def test_missing_glyph_user_warning_is_ignored():
    assert not _emit(UserWarning, "Glyph 12354 (\\N{HIRAGANA LETTER A}) missing from font(s) DejaVu Sans.")
    assert not _emit(UserWarning, "Glyph 12354 missing from current font.")


def test_unrelated_user_warning_is_still_emitted():
    assert len(_emit(UserWarning, "something unrelated")) == 1


def test_no_blanket_deprecation_ignore_in_entry_point():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "py" / "main.py").read_text(encoding="utf-8")
    assert 'simplefilter("ignore"' not in text
