import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest
from matplotlib import font_manager

from mplgui import fonts

pytestmark = pytest.mark.unit


def test_configure_rcparams_uses_priority_list():
    with mpl.rc_context():
        fonts.configure_rcparams()
        assert plt.rcParams["font.sans-serif"] == fonts.SANS_SERIF_PRIORITY
        assert plt.rcParams["font.family"] == ["sans-serif"] and plt.rcParams["axes.unicode_minus"] is False


def test_priority_starts_with_noto_sans_cjk_jp():
    assert fonts.SANS_SERIF_PRIORITY[:2] == ["Noto Sans CJK JP", "Noto Sans JP"]
    assert fonts.SANS_SERIF_PRIORITY[-1] == "DejaVu Sans"


def test_register_font_file_leaves_the_same_order_as_generated_scripts():
    path = font_manager.findfont("DejaVu Sans")
    with mpl.rc_context():
        plt.rcParams["font.sans-serif"] = ["Arial"]  # 任意の状態から始めても
        fonts.register_font_file(path)
        assert plt.rcParams["font.sans-serif"] == fonts.SANS_SERIF_PRIORITY
