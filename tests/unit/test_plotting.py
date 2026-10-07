import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle

from mplgui.errors import UserError
from mplgui.plotting import create_figure, get_per_series_xy_data, get_plot_data, resolve_series_requests
from mplgui.settings import default_settings, parse_settings, series_to_legacy

pytestmark = pytest.mark.unit


@pytest.fixture
def df():
    t = np.arange(20, dtype=float)
    return pd.DataFrame({"t": t, "a": np.sin(t), "b": t * 2.0, "name": [f"n{i}" for i in range(20)]})


def settings_with(mutator=None, series=None):
    raw = default_settings()
    if series is not None:
        raw["series"] = series
    if mutator:
        mutator(raw)
    return parse_settings(raw)


def build(df, mutator=None, series=None):
    result = create_figure(df, settings_with(mutator, series))
    return result


def close(result):
    plt.close(result.fig)


def lines(ax):
    return [ln for ln in ax.get_lines()]


def bars(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle)]


def test_line_two_series():
    r = build(
        pd.DataFrame({"t": range(10), "a": range(10), "b": range(10, 20)}),
        series=[{"x": "__idx__0", "y": "__idx__1", "color": "#005AFF"}, {"x": "__idx__0", "y": "__idx__2", "color": "#03AF7A"}],
    )
    try:
        ax = r.fig.axes[0]
        assert len(r.fig.axes) == 1 and len(lines(ax)) == 2 and r.plotted_count == 2
        assert lines(ax)[0].get_color().lower() == "#005aff" and lines(ax)[0].get_linewidth() == 2
        assert lines(ax)[0].get_marker() in ("", "None", None)  # 点サイズ自動(line)=0 は点なし
        assert not ax.collections
    finally:
        close(r)


def test_line_marker_shown_when_size_positive():
    r = build(pd.DataFrame({"a": [1.0, 2.0, 3.0]}), series=[{"markerSize": 9}])
    try:
        ln = lines(r.fig.axes[0])[0]
        assert ln.get_marker() == "o" and ln.get_markersize() == pytest.approx(3.0)
    finally:
        close(r)


def test_line_style_and_width():
    r = build(pd.DataFrame({"a": [1.0, 2.0, 3.0]}), series=[{"lineStyle": "dashed", "lineWidth": 3.5}])
    try:
        ln = lines(r.fig.axes[0])[0]
        assert ln.get_linestyle() == "--" and ln.get_linewidth() == 3.5
    finally:
        close(r)


def test_scatter_creates_path_collections():
    r = build(
        pd.DataFrame({"x": range(5), "a": range(5), "b": range(5)}),
        mutator=lambda s: s["plot"].__setitem__("type", "scatter"),
        series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__2", "markerSize": 50}],
    )
    try:
        ax = r.fig.axes[0]
        cols = [c for c in ax.collections if isinstance(c, PathCollection)]
        assert len(cols) == 2 and not lines(ax)
        assert cols[0].get_sizes()[0] == 24  # 自動 → scatter の既定 24
        assert cols[1].get_sizes()[0] == 50
    finally:
        close(r)


def test_scatter_size_zero_is_corrected_to_24():
    r = build(
        pd.DataFrame({"a": [1.0, 2.0]}),
        mutator=lambda s: s["plot"].__setitem__("type", "scatter"),
        series=[{"markerSize": 0}],
    )
    try:
        assert r.fig.axes[0].collections[0].get_sizes()[0] == 24
    finally:
        close(r)


def test_bar_single_series_uses_x_column(df):
    r = build(
        df.head(6),
        mutator=lambda s: s["plot"].update(type="bar", xColumn="__idx__0"),
        series=[{"y": "__idx__1"}],
    )
    try:
        assert len(bars(r.fig.axes[0])) == 6
    finally:
        close(r)


def test_bar_multiple_series_grouped(df):
    r = build(
        df.head(5),
        mutator=lambda s: s["plot"].update(type="bar"),
        series=[{"y": "__idx__1"}, {"y": "__idx__2"}],
    )
    try:
        ax = r.fig.axes[0]
        assert len(bars(ax)) == 10 and r.plotted_count == 2
        assert set(range(5)) <= set(ax.get_xticks())
    finally:
        close(r)


def test_secondary_axis_uses_twinx():
    d = pd.DataFrame({"x": range(10), "a": range(10), "b": [v * 100 for v in range(10)]})
    r = build(
        d,
        series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__2", "secondaryAxis": True}],
        mutator=lambda s: s["axes"]["y2"].update(label="右軸"),
    )
    try:
        assert len(r.fig.axes) == 2
        ax, ax2 = r.fig.axes
        assert len(lines(ax)) == 1 and len(lines(ax2)) == 1
        assert ax2.get_ylabel() == "右軸"
        assert ax2.get_shared_x_axes().joined(ax, ax2)
        # 凡例は両軸のハンドルを統合する
        assert [t.get_text() for t in ax.get_legend().get_texts()] == ["a [1]", "b [2]"]
        # ヒゲ: 主軸は下・左、第2軸は右のみ
        assert ax2.yaxis.get_ticks_position() in ("right", "default") and ax.xaxis.get_ticks_position() == "bottom"
    finally:
        close(r)


def test_no_second_axis_without_secondary_series(df):
    r = build(df, series=[{"y": "__idx__1"}])
    try:
        assert len(r.fig.axes) == 1
    finally:
        close(r)


@pytest.mark.parametrize("loc, expect_legend", [("best", True), ("upper left", True), ("none", False)])
def test_legend_presence(df, loc, expect_legend):
    r = build(df, mutator=lambda s: s["plot"]["legend"].__setitem__("location", loc), series=[{"y": "__idx__1"}])
    try:
        legend = r.fig.axes[0].get_legend()
        assert (legend is not None) is expect_legend
        if expect_legend:
            assert [t.get_text() for t in legend.get_texts()] == ["a [1]"]
    finally:
        close(r)


def test_legend_custom_label(df):
    r = build(df, series=[{"y": "__idx__1", "label": "電圧"}])
    try:
        assert [t.get_text() for t in r.fig.axes[0].get_legend().get_texts()] == ["電圧"]
    finally:
        close(r)


def test_grid_flags(df):
    def grids(ax):
        return (
            any(ln.get_visible() for ln in ax.get_xgridlines()),
            any(ln.get_visible() for ln in ax.get_ygridlines()),
        )

    r = build(df, mutator=lambda s: s["plot"]["grid"].update(major=True))
    try:
        assert grids(r.fig.axes[0]) == (True, True)
    finally:
        close(r)
    r = build(df)
    try:
        assert grids(r.fig.axes[0]) == (False, False)
    finally:
        close(r)
    r = build(df, mutator=lambda s: s["plot"]["grid"].update(minor=True))
    try:
        ax = r.fig.axes[0]
        assert ax.xaxis.get_minor_ticks()[0].gridline.get_visible()
        assert not any(ln.get_visible() for ln in ax.get_xgridlines())  # 主目盛線は出さない
    finally:
        close(r)


def test_log_scale_and_limits(df):
    def m(s):
        s["axes"]["y"].update(scale="log", min=0.5, max=100)
        s["axes"]["x"].update(min=2, max=10)

    r = build(df.assign(a=np.arange(1, 21)), mutator=m, series=[{"y": "__idx__1"}])
    try:
        ax = r.fig.axes[0]
        assert ax.get_yscale() == "log" and ax.get_xscale() == "linear"
        assert ax.get_ylim() == (0.5, 100) and ax.get_xlim() == (2, 10)
    finally:
        close(r)


def test_figure_size_title_and_labels(df):
    def m(s):
        s["plot"].update(title="タイトル", fontSize=12)
        s["plot"]["figure"].update(width=5, height=3)
        s["axes"]["x"]["label"] = "X軸"
        s["axes"]["y"]["label"] = "Y軸"

    r = build(df, mutator=m, series=[{"y": "__idx__1"}])
    try:
        ax = r.fig.axes[0]
        assert tuple(r.fig.get_size_inches()) == (5.0, 3.0)
        assert ax.get_title() == "タイトル" and ax.title.get_fontsize() == 14
        assert ax.get_xlabel() == "X軸" and ax.get_ylabel() == "Y軸" and ax.xaxis.label.get_fontsize() == 12
    finally:
        close(r)


def test_default_labels_come_from_columns(df):
    r = build(df, series=[{"x": "__idx__0", "y": "__idx__1"}])
    try:
        ax = r.fig.axes[0]
        assert ax.get_xlabel() == "t" and ax.get_ylabel() == "a [1]"
    finally:
        close(r)


def test_ticks_inward(df):
    r = build(df)
    try:
        ax = r.fig.axes[0]
        assert ax.xaxis.get_major_ticks()[0]._pad is not None
        assert not ax.xaxis.get_major_ticks()[0].tick2line.get_visible()  # 上側のヒゲなし
        assert not ax.yaxis.get_major_ticks()[0].tick2line.get_visible()  # 右側のヒゲなし
    finally:
        close(r)


def test_margins_applied(df):
    r = build(df, mutator=lambda s: s["plot"]["margins"].update(left=0.2, right=0.9))
    try:
        assert r.fig.subplotpars.left == pytest.approx(0.2) and r.fig.subplotpars.right == pytest.approx(0.9)
    finally:
        close(r)


def test_skip_rows_excludes_leading_rows():
    d = pd.DataFrame({"a": [100.0, 200.0, 1.0, 2.0, 3.0]})
    r = build(d, mutator=lambda s: s["plot"].__setitem__("skipRows", 2))
    try:
        assert r.skip_rows == 2
        assert list(lines(r.fig.axes[0])[0].get_ydata()) == [1.0, 2.0, 3.0]
    finally:
        close(r)


def test_skip_rows_too_large(df):
    with pytest.raises(UserError) as info:
        build(df, mutator=lambda s: s["plot"].__setitem__("skipRows", 20))
    assert "スキップ" in info.value.message


def test_no_plottable_data_raises_and_closes_figure():
    before = set(plt.get_fignums())
    with pytest.raises(UserError):
        build(pd.DataFrame({"a": ["x", "y", "z"]}), series=[{"y": "__idx__0"}])
    assert set(plt.get_fignums()) == before  # 失敗しても Figure は残らない


def test_column_out_of_range_is_user_error(df):
    with pytest.raises(UserError) as info:
        build(df, series=[{"y": "__idx__99"}])
    assert "99" in info.value.message


def test_duplicate_column_names_resolved_by_index():
    d = pd.DataFrame([[1, 10, 100], [2, 20, 200], [3, 30, 300]], columns=["温度", "温度", "値"])
    r = build(d, series=[{"y": "__idx__0"}, {"y": "__idx__1"}])
    try:
        ys = [list(ln.get_ydata()) for ln in lines(r.fig.axes[0])]
        assert ys == [[1, 2, 3], [10, 20, 30]]
    finally:
        close(r)


def test_auto_y_assigns_unused_numeric_columns(df):
    r = build(df, series=[{}, {}])
    try:
        ys = [list(ln.get_ydata()) for ln in lines(r.fig.axes[0])]
        assert ys[0] == list(df["t"]) and ys[1] == list(df["a"])  # 数値列を順に割り当てる
    finally:
        close(r)


def test_legacy_helpers(df):
    s = settings_with(series=[{"y": ""}, {"y": "__idx__2"}])
    legacy = series_to_legacy(s)
    assert resolve_series_requests(df, legacy) == ["__idx__0", "__idx__2"]
    entries, xlabel = get_per_series_xy_data(df, legacy)
    assert xlabel == "index" and len(entries) == 2 and entries[1]["data_label"] == "b [2]"
    x, xl, es = get_plot_data(df, legacy, "__idx__0")
    assert xl == "t" and len(es) == 2 and list(x) == list(df["t"])


# ---------------------------------------------------------------- A7: dropped values


def _csv_df(name="non_numeric.csv"):
    from pathlib import Path

    from mplgui.loader import load_file

    path = Path(__file__).resolve().parents[1] / "fixtures" / name
    return load_file(path.read_bytes(), name, "", True).df


def test_dropped_values_are_reported_per_series():
    df = _csv_df()
    r = build(df, series=[
        {"x": "__idx__0", "y": "__idx__2"},   # 電圧: 数値列（空欄・N/A は欠損値でありカウントしない）
        {"x": "__idx__0", "y": "__idx__1"},   # 金額: "1,234" 形式 → 全件変換不可
        {"x": "__idx__0", "y": "__idx__3"},   # 単位付き: "1 mV"
    ])
    try:
        assert r.plotted_count == 1
        msgs = {w["series"]: w["message"] for w in r.warnings}
        assert set(msgs) == {2, 3}
        assert msgs[2].startswith("系列2（金額）: 数値に変換できない値が20件あったため、その行を除外しました（例: ")
        assert '"1,234"' in msgs[2] and '"2,468"' in msgs[2] and '"3,702"' in msgs[2] and '"4,936"' not in msgs[2]
        assert '"1 mV"' in msgs[3] and msgs[3].endswith("）。")
    finally:
        close(r)


def test_blank_cells_are_not_counted_as_dropped():
    df = pd.DataFrame({"t": [1, 2, 3, 4], "v": ["1", "", "  ", "x"]})
    r = build(df, series=[{"x": "__idx__0", "y": "__idx__1"}])
    try:
        assert len(r.warnings) == 1
        assert "1件" in r.warnings[0]["message"] and '"x"' in r.warnings[0]["message"]
        assert r.warnings[0]["series"] == 1
    finally:
        close(r)


def test_no_warning_for_clean_data(df):
    r = build(df)
    try:
        assert r.warnings == []
    finally:
        close(r)


def test_x_column_dropped_values_are_reported():
    df = pd.DataFrame({"x": ["1", "2", "3", "oops", "5"], "y": [1.0, 2.0, 3.0, 4.0, 5.0]})
    r = build(df, series=[{"x": "__idx__0", "y": "__idx__1"}])
    try:
        assert r.plotted_count == 1
        assert "系列1のX列（x）" in r.warnings[0]["message"] and '"oops"' in r.warnings[0]["message"]
        assert len(lines(r.fig.axes[0])[0].get_xdata()) == 4
    finally:
        close(r)


def test_all_values_dropped_error_mentions_cause():
    df = _csv_df()
    with pytest.raises(UserError) as info:
        build(df, series=[{"x": "__idx__0", "y": "__idx__1"}])
    assert "数値に変換できない値" in info.value.message


def test_bar_reports_dropped_values():
    df = pd.DataFrame({"x": list("abcd"), "y": ["1", "2", "bad", "4"]})
    r = build(df, lambda s: s["plot"].update(type="bar"), series=[{"y": "__idx__1"}])
    try:
        assert "系列1（y）" in r.warnings[0]["message"]
    finally:
        close(r)
