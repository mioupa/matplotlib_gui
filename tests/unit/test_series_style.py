"""Phase 5b: 系列のスタイル（G3）。点の形・不透明度・塗りつぶし帯。生成コードを CPython で実行した図を検査する。"""
import numpy as np
import pandas as pd
import pytest

from mplgui.errors import UserError
from mplgui.settings import parse_settings
from style_helpers import Built, frame, plan_of, raw_settings, series

pytestmark = pytest.mark.unit


def fill(lower=2, upper=3, alpha=None):
    d = {"lower": f"__idx__{lower}", "upper": f"__idx__{upper}"}
    if alpha is not None:
        d["alpha"] = alpha
    return d


def series_line(ax):
    return [ln for ln in ax.lines if not ln.get_label().startswith("_")][0]


# ---------------------------------------------------------------- 点の形


def test_line_auto_marker_keeps_phase4_behavior():
    assert plan_of().series[0].marker == ""
    p = plan_of(series_list=[series(markerSize=16)]).series[0]
    assert p.marker == "o" and p.marker_size == 16.0


def test_line_shape_without_size_uses_scatter_default_area():
    p = plan_of(series_list=[series(marker="s")]).series[0]
    assert p.marker == "s" and p.marker_size == 24.0


def test_line_shape_with_size_keeps_size():
    p = plan_of(series_list=[series(marker="^", markerSize=9)]).series[0]
    assert p.marker == "^" and p.marker_size == 9.0


def test_line_none_ignores_marker_size():
    p = plan_of(series_list=[series(marker="none", markerSize=30)]).series[0]
    assert p.marker == ""


def test_scatter_marker_plan():
    assert plan_of(series_list=[series()], plot_type="scatter").series[0].marker == ""
    p = plan_of(series_list=[series(marker="D")], plot_type="scatter").series[0]
    assert p.marker == "D" and p.marker_size == 24.0


def test_line_shape_draws_marker(tmp_path):
    b = Built(tmp_path, series_list=[series(marker="s")])
    assert 'marker="s", markersize=24.0 ** 0.5' in b.script.text

    def check(fig):
        line = series_line(fig.axes[0])
        assert line.get_marker() == "s" and line.get_markersize() == pytest.approx(24.0**0.5)

    summary = b.check(check)
    assert summary[0]["markers"] == ["s"]


def test_line_none_draws_no_marker(tmp_path):
    b = Built(tmp_path, series_list=[series(marker="none", markerSize=30)])
    assert "marker=" not in b.script.text.split("# ==== 4.")[1].split("# ==== 5.")[0]
    summary = b.check(lambda fig: None)
    assert summary[0]["markers"] == ["None"]


def test_scatter_shape_changes_marker_path(tmp_path):
    circle = Built(tmp_path, series_list=[series()], plot_type="scatter")
    square = Built(tmp_path, series_list=[series(marker="s")], plot_type="scatter")
    assert 'marker="s"' in square.script.text and "marker=" not in circle.script.text.split("# ==== 4.")[1].split("# ==== 5.")[0]
    with circle.full() as a, square.full() as b:
        pa = a.fig.axes[0].collections[0].get_paths()[0]
        pb = b.fig.axes[0].collections[0].get_paths()[0]
        assert len(pa.vertices) != len(pb.vertices)
    square.check(lambda fig: None)


def test_scatter_none_is_error():
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(marker="none")], "scatter"))
    assert e.value.field == "系列1の点の形"


def test_marker_choice_validated():
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(marker="zzz")]))
    assert e.value.field == "系列1の点の形"


# ---------------------------------------------------------------- 不透明度


def test_alpha_default_writes_nothing(tmp_path):
    b = Built(tmp_path)
    assert "alpha=" not in b.script.text.split("# ==== 4.")[1].split("# ==== 5.")[0]


@pytest.mark.parametrize("plot_type", ["line", "scatter", "bar"])
def test_alpha_is_applied(tmp_path, plot_type):
    b = Built(tmp_path, series_list=[series(alpha=0.5)], plot_type=plot_type)
    assert "alpha=0.5" in b.script.text

    def check(fig):
        ax = fig.axes[0]
        if plot_type == "line":
            assert series_line(ax).get_alpha() == 0.5
        elif plot_type == "scatter":
            assert ax.collections[0].get_alpha() == 0.5
        else:
            assert all(p.get_alpha() == 0.5 for p in ax.patches)

    b.check(check)


def test_alpha_multi_bar(tmp_path):
    b = Built(tmp_path, series_list=[series(1, alpha=0.4), series(4)], plot_type="bar")
    with b.full() as run:
        patches = run.fig.axes[0].patches
        assert {p.get_alpha() for p in patches[: len(patches) // 2]} == {0.4}
        assert {p.get_alpha() for p in patches[len(patches) // 2 :]} == {None}
    b.check(lambda fig: None)


@pytest.mark.parametrize("value", [-0.1, 1.5, "abc"])
def test_alpha_validated(value):
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(alpha=value)]))
    assert e.value.field == "系列1の不透明度"


def test_alpha_summary(tmp_path):
    summary = Built(tmp_path, series_list=[series(alpha=0.3)]).check(lambda fig: None)
    assert summary[0]["alphas"] == [0.3]


# ---------------------------------------------------------------- 塗りつぶし帯


def test_no_band_by_default():
    assert plan_of().series[0].fill is None


def test_band_plan_resolves_columns():
    p = plan_of(series_list=[series(fill=fill(alpha=0.4))]).series[0]
    assert (p.fill.lower_index, p.fill.upper_index, p.fill.alpha) == (2, 3, 0.4)
    assert p.fill.lower_label == "lo [2]"


def test_band_is_drawn_before_series(tmp_path):
    b = Built(tmp_path, series_list=[series(fill=fill())])
    text = b.script.text
    assert text.index("fill_between") < text.index("ax.plot(x[ok]")
    assert 'label="_fill"' in text and "alpha=0.25, linewidth=0" in text

    def check(fig):
        ax = fig.axes[0]
        poly = [c for c in ax.collections if c.get_label() == "_fill"]
        assert len(poly) == 1
        ys = poly[0].get_paths()[0].vertices[:, 1]
        assert ys.min() == pytest.approx(8.0) and ys.max() == pytest.approx(31.0)
        assert poly[0].get_alpha() == 0.25
        assert "_fill" not in [t.get_text() for t in ax.get_legend().get_texts()]

    summary = b.check(check)
    assert summary[0]["bands"] == 1


def test_band_scatter_and_secondary_axis(tmp_path):
    b = Built(tmp_path, series_list=[series(fill=fill(), secondaryAxis=True)], plot_type="scatter")
    assert "ax2.fill_between" in b.script.text
    b.check(lambda fig: None)


def test_band_missing_values_break_the_band_and_warn(tmp_path):
    df = frame().astype({"lo": object})
    df.loc[3, "lo"] = "x"
    df.loc[4, "lo"] = np.nan
    b = Built(tmp_path, df=df, series_list=[series(fill=fill())])
    warnings = [w["message"] for w in b.plan.warnings]
    assert len(warnings) == 1 and "塗りつぶし帯（下端）" in warnings[0] and "1件" in warnings[0] and '"x"' in warnings[0]
    b.check(lambda fig: None)


def test_band_warning_counts_only_plotted_rows(tmp_path):
    df = frame().astype({"lo": object})
    df.loc[3, "lo"] = "x"
    df.loc[3, "v"] = np.nan  # この行は描かない
    b = Built(tmp_path, df=df, series_list=[series(fill=fill())])
    assert not b.plan.warnings


def test_band_warning_has_thousands_hint():
    df = frame().astype({"lo": object})
    df.loc[3, "lo"] = "1,234"
    p = plan_of(df=df, series_list=[series(fill=fill())])
    assert "桁区切り" in p.warnings[0]["message"]


def test_band_column_out_of_range():
    with pytest.raises(UserError) as e:
        plan_of(series_list=[series(fill=fill(lower=9))])
    assert e.value.field == "系列1の塗りつぶし帯"


def test_band_one_side_empty_is_error():
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(fill={"lower": "__idx__2", "upper": ""})]))
    assert e.value.field == "系列1の塗りつぶし帯"


def test_band_datetime_x(tmp_path):
    df = frame()
    df["d"] = pd.date_range("2026-01-01", periods=len(df)).strftime("%Y-%m-%d")
    b = Built(tmp_path, df=df, series_list=[series(x=5, fill=fill())])
    assert b.plan.series[0].datetime_x
    b.check(lambda fig: None)


def test_band_text_x(tmp_path):
    df = frame()
    df["c"] = [f"k{i}" for i in range(len(df))]
    b = Built(tmp_path, df=df, series_list=[series(x=5, fill=fill())])
    assert b.plan.series[0].categorical_x
    b.check(lambda fig: None)


def test_band_extents_feed_tick_estimate():
    # 帯の上端（最大 37）まで範囲に入るので、間隔 0.1 だと 100 本を超える。帯が無ければ v の最大 28 でも超える点は同じだが、見積もりが帯を含むこと
    from mplgui.dataprep import MAX_MAJOR_TICKS

    def mutate(raw):
        raw["axes"]["y"]["majorStep"] = 0.36

    ok = plan_of(series_list=[series()], mutate=mutate)  # (28-10)*1.1/0.36+1 = 56
    assert ok.axes.y.major_step == 0.36
    with pytest.raises(UserError):
        plan_of(df=frame().assign(hi=lambda d: d["hi"] * 20), series_list=[series(fill=fill())], mutate=mutate)
    assert MAX_MAJOR_TICKS == 100


def test_bar_ignores_marker_and_fill(tmp_path):
    # 棒グラフでは点の形・帯は隠れているので、不正な値でも検証せず、使わない
    s = series(marker="zzz", fill={"lower": "oops", "upper": ""}, alpha=0.5)
    b = Built(tmp_path, series_list=[s], plot_type="bar")
    assert "fill_between" not in b.script.text and "marker" not in b.script.text
    assert "alpha=0.5" in b.script.text


def test_band_label_with_injection(tmp_path):
    df = frame().rename(columns={"lo": 'x"\n__import__("os")'})
    b = Built(tmp_path, df=df, series_list=[series(fill=fill())])
    compile(b.script.text, "plot.py", "exec")
    assert "\n__import__" not in b.script.text
    b.check(lambda fig: None)
