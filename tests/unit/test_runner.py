import pandas as pd
import pytest

import matplotlib.pyplot as plt

from mplgui.errors import UserError
from mplgui.runner import (
    DEFAULT_CUSTOM_PLOT_CODE,
    build_filename,
    figure_to_bytes,
    figure_to_data_uri,
    make_figure,
    run_custom_code,
)
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit


@pytest.fixture
def fig():
    f, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    yield f
    plt.close(f)


@pytest.fixture
def df():
    return pd.DataFrame({"t": [0.0, 1.0, 2.0, 3.0], "v": [1.0, 2.0, 3.0, 4.0], "w": [4.0, 3.0, 2.0, 1.0]})


def settings(**plot):
    raw = default_settings()
    raw["plot"].update(plot)
    return parse_settings(raw)


@pytest.mark.parametrize(
    "fmt, magic, mime, ext",
    [
        ("png", b"\x89PNG\r\n\x1a\n", "image/png", "png"),
        ("jpg", b"\xff\xd8\xff", "image/jpeg", "jpg"),
        ("svg", b"<?xml", "image/svg+xml", "svg"),
        ("pdf", b"%PDF-", "application/pdf", "pdf"),
    ],
)
def test_figure_to_bytes_magic(fig, fmt, magic, mime, ext):
    data, got_mime, got_ext = figure_to_bytes(fig, fmt)
    assert data.startswith(magic) and got_mime == mime and got_ext == ext


def test_transparent_only_png_and_svg(fig):
    for fmt in ("png", "svg"):
        figure_to_bytes(fig, fmt, transparent=True)
    for fmt in ("jpg", "pdf"):
        with pytest.raises(UserError) as info:
            figure_to_bytes(fig, fmt, transparent=True)
        assert "背景透過" in info.value.message


def test_transparent_png_has_alpha(fig):
    import io

    from matplotlib import image as mpimg

    data, _, _ = figure_to_bytes(fig, "png", transparent=True)
    arr = mpimg.imread(io.BytesIO(data))
    assert arr.shape[2] == 4 and arr[0, 0, 3] == 0
    data, _, _ = figure_to_bytes(fig, "png", transparent=False)
    assert mpimg.imread(io.BytesIO(data))[0, 0, 3] == 1


def test_unknown_format_is_user_error(fig):
    with pytest.raises(UserError):
        figure_to_bytes(fig, "gif")


def test_data_uri(fig):
    uri, ext = figure_to_data_uri(fig, "png", dpi=100)
    assert uri.startswith("data:image/png;base64,") and ext == "png"
    uri, ext = figure_to_data_uri(fig, "svg")
    assert uri.startswith("data:image/svg+xml;base64,") and ext == "svg"


def test_build_filename():
    assert build_filename("", "png") == "plot.png"
    assert build_filename(None, "png") == "plot.png"
    assert build_filename("  ", "svg") == "plot.svg"
    assert build_filename("fig.1.svg", "pdf") == "fig.1.pdf"
    assert build_filename("name.", "jpg") == "name.jpg"
    assert build_filename("結果", "png") == "結果.png"
    assert build_filename(".png", "png") == "plot.png"


def test_default_custom_code_runs(df):
    r = run_custom_code(DEFAULT_CUSTOM_PLOT_CODE, df, settings())
    try:
        assert r.plotted_count == 1 and r.skip_rows == 0
        assert len(r.fig.axes[0].get_lines()) == 1
    finally:
        plt.close(r.fig)


def test_custom_code_namespace(df):
    code = """
assert set(['df','current_df','settings','ctx','series_settings','get_plot_data','get_per_series_xy_data',
            'resolve_series_requests','plt','pd','fig','plotted_count','skip_rows']) <= set(globals()) | set(dir())
assert list(df.columns) == ['t', 'v', 'w'] and len(df) == 2 and len(current_df) == 4 and skip_rows == 2
assert settings['plot_type'] == 'line' and 'series_settings' in settings and settings['skip_rows'] == 2
assert series_settings[0]['y_request'] == '' and ctx['df'] is not None and 'get_plot_data' in ctx['helpers']
assert resolve_series_requests(df, series_settings) == ['__idx__0']
x, label, entries = get_plot_data(df, series_settings)
fig, ax = plt.subplots()
ax.plot(df['t'], df['v'])
"""
    r = run_custom_code(code, df, settings(skipRows=2))
    plt.close(r.fig)
    assert r.skip_rows == 2


def test_custom_code_gui_overrides_still_apply(df):
    raw = default_settings()
    raw["plot"]["title"] = "GUI題"
    raw["axes"]["x"]["label"] = "GUI X"
    raw["plot"]["legend"]["location"] = "none"
    raw["axes"]["y"].update(min=0, max=10)
    code = "fig, ax = plt.subplots()\nax.plot([1, 2], [3, 4], label='a')\nax.set_title('code')\nax.legend()\n"
    r = run_custom_code(code, df, parse_settings(raw))
    try:
        ax = r.fig.axes[0]
        assert ax.get_title() == "GUI題" and ax.get_xlabel() == "GUI X"
        assert ax.get_legend() is None and ax.get_ylim() == (0, 10)
    finally:
        plt.close(r.fig)


def test_custom_code_errors(df):
    with pytest.raises(UserError) as info:
        run_custom_code("   ", df, settings())
    assert "空" in info.value.message
    with pytest.raises(UserError) as info:
        run_custom_code("x = 1", df, settings())
    assert "fig" in info.value.message
    with pytest.raises(UserError) as info:
        run_custom_code("fig = 3", df, settings())
    assert "Figure" in info.value.message
    before = set(plt.get_fignums())
    with pytest.raises(UserError) as info:
        run_custom_code("fig, ax = plt.subplots()\nraise ValueError('boom')", df, settings())
    assert "カスタムコードの実行に失敗しました" in info.value.message and "boom" in info.value.message
    assert info.value.detail and "Traceback" in info.value.detail
    assert set(plt.get_fignums()) == before  # 失敗時に作りかけの Figure を残さない
    with pytest.raises(UserError):
        run_custom_code("fig, ax = plt.subplots()", df, settings(skipRows=4))  # スキップ行数 >= 行数


def test_custom_code_empty_figure_is_error(df):
    before = set(plt.get_fignums())
    with pytest.raises(UserError):
        run_custom_code("fig, ax = plt.subplots()", df, settings())
    assert set(plt.get_fignums()) == before


def test_make_figure_dispatch(df):
    r = make_figure(df, settings())
    plt.close(r.fig)
    assert r.plotted_count == 1
    r = make_figure(df, settings(), "fig, ax = plt.subplots()\nax.plot([0,1],[0,1])")
    plt.close(r.fig)
    assert r.plotted_count == 1


def test_filename_invalid_characters_are_replaced():
    assert build_filename('a/b:c*?.png', "svg") == "a_b_c__.svg"


def test_tight_layout_failure_is_japanese_user_error(monkeypatch, df):
    from matplotlib.figure import Figure

    def boom(self, *a, **k):
        raise RuntimeError("tight failed")

    monkeypatch.setattr(Figure, "tight_layout", boom)
    with pytest.raises(UserError) as info:
        make_figure(df, settings())
    assert "レイアウト" in info.value.message and "tight failed" in info.value.detail


# ---------------------------------------------------------------- PlaceHolderLayoutEngine の除去


def _default_fig(df):
    from mplgui.plotting import create_figure

    return create_figure(df, parse_settings(default_settings())).fig


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_dropping_placeholder_engine_keeps_output_identical(df, fmt):
    import io

    import matplotlib as mpl
    from matplotlib.layout_engine import PlaceHolderLayoutEngine

    from mplgui.runner import drop_placeholder_layout_engine

    meta = {"png": {"Software": None}, "svg": {"Date": None}, "pdf": {"CreationDate": None}}[fmt]
    kw = {"dpi": 120} if fmt == "png" else {}

    def render(drop):
        fig = _default_fig(df)
        try:
            assert isinstance(fig.get_layout_engine(), PlaceHolderLayoutEngine)
            if drop:
                drop_placeholder_layout_engine(fig)
                assert fig.get_layout_engine() is None
            buf = io.BytesIO()
            with mpl.rc_context({"svg.hashsalt": "fixed"}):
                fig.savefig(buf, format=fmt, metadata=meta, **kw)
            return buf.getvalue()
        finally:
            plt.close(fig)

    assert render(False) == render(True)


def test_real_layout_engine_is_kept(df):
    from mplgui.runner import drop_placeholder_layout_engine

    fig, ax = plt.subplots(layout="constrained")
    ax.plot([0, 1], [0, 1])
    try:
        drop_placeholder_layout_engine(fig)
        assert fig.get_layout_engine() is not None
        assert fig.get_layout_engine().__class__.__name__ == "ConstrainedLayoutEngine"
        figure_to_bytes(fig, "png")
        assert fig.get_layout_engine().__class__.__name__ == "ConstrainedLayoutEngine"
    finally:
        plt.close(fig)


def test_figure_to_bytes_draws_fewer_times(df, monkeypatch):
    from matplotlib.figure import Figure

    calls = {"n": 0}
    orig = Figure.draw

    def counting(self, *a, **k):
        calls["n"] += 1
        return orig(self, *a, **k)

    fig = _default_fig(df)
    try:
        monkeypatch.setattr(Figure, "draw", counting)
        figure_to_bytes(fig, "png")
        assert calls["n"] == 1
    finally:
        plt.close(fig)
