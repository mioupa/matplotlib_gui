"""Phase 5a: 目盛（G2）・枠線・日時の範囲。dataprep の AxisPlan と、生成コードを CPython で実行した結果を検査する。"""
import ast
import contextlib
import dataclasses
import re

import numpy as np
import pandas as pd
import pytest

from mplgui import codegen
from mplgui.codegen import generate_script
from mplgui.dataprep import AxesPlan, AxisPlan, MAX_MAJOR_TICKS, plan_plot
from mplgui.errors import UserError
from mplgui.loader import SourceInfo, load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit


def numeric_frame(n=11):
    t = np.linspace(0, 1, n)
    return pd.DataFrame({"t": t, "v": t * 1e6, "w": t * 3 + 1, "cat": [f"区分{i % 6}" for i in range(n)]})


def date_frame(days=30, freq="D"):
    stamps = pd.date_range("2026-01-01", periods=days, freq=freq)
    return pd.DataFrame({"日時": stamps.strftime("%Y-%m-%d %H:%M:%S"), "v": np.arange(days, dtype=float)})


def S(y, **kw):
    d = {"x": "", "y": f"__idx__{y}"}
    d.update(kw)
    return d


class Built:
    def __init__(self, tmp_path, df, mutate=None, series=None):
        self.dir = tmp_path
        df.to_csv(tmp_path / "d.csv", index=False, encoding="utf-8")
        self.loaded = load_file((tmp_path / "d.csv").read_bytes(), "d.csv", "", True)
        raw = default_settings()
        if series is not None:
            raw["series"] = series
        if mutate:
            mutate(raw)
        self.settings = parse_settings(raw)
        self.plan = plan_plot(self.loaded.df, self.settings)
        self.script = generate_script(self.settings, self.loaded.source, self.plan)

    @contextlib.contextmanager
    def full(self):
        with run_script(self.script.text, cwd=self.dir) as run:
            yield run

    @contextlib.contextmanager
    def auto(self):
        with run_script(self.script.auto_render_text(), injected={"df": self.loaded.df}) as run:
            yield run

    def summaries(self):
        with self.full() as run:
            full = figure_summary(run.fig)
        with self.auto() as run:
            auto = figure_summary(run.fig)
        return full, auto

    def summary(self):
        """全体を実行した図の要約。自動描画用の変種の要約と一致することも確かめる。"""
        full, auto = self.summaries()
        assert full == auto
        return full


def plan_of(df, mutate=None, series=None):
    raw = default_settings()
    if series is not None:
        raw["series"] = series
    if mutate:
        mutate(raw)
    loaded = load_file(df.to_csv(index=False).encode("utf-8"), "d.csv", "", True)  # 日時の列の変換も loader と同じにする
    return plan_plot(loaded.df, parse_settings(raw))


def axis(key, **kw):
    def m(raw):
        raw["axes"][key].update(kw)
    return m


def both(*mutators):
    def m(raw):
        for f in mutators:
            f(raw)
    return m


def visible_labels(ax, which="x"):
    """表示範囲の中の主目盛の (位置, ラベル)。"""
    axis_ = ax.xaxis if which == "x" else ax.yaxis
    lo, hi = sorted(ax.get_xlim() if which == "x" else ax.get_ylim())
    labels = [t.get_text() for t in (ax.get_xticklabels() if which == "x" else ax.get_yticklabels())]
    return [(loc, lab) for loc, lab in zip(axis_.get_majorticklocs(), labels) if lo - 1e-9 <= loc <= hi + 1e-9]


# ---------------------------------------------------------------- AxisPlan: kinds and applicability


def test_axis_kinds():
    num = numeric_frame()
    p = plan_of(num, series=[S(1, x="__idx__0")])
    assert p.axes.x.kind == "number" and p.axes.y.kind == "number" and p.axes.y2 is None
    p = plan_of(num, both(axis("x", scale="log"), axis("y", scale="log")), [S(1, x="__idx__0")])
    assert p.axes.x.kind == "log" and p.axes.y.kind == "log"
    assert plan_of(num, series=[S(1, x="__idx__3")]).axes.x.kind == "category"
    assert plan_of(date_frame(), series=[S(1, x="__idx__0")]).axes.x.kind == "datetime"
    p = plan_of(num, series=[S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)], mutate=axis("y2", scale="log"))
    assert p.axes.y2 is not None and p.axes.y2.kind == "log"


def test_bar_axis_kinds():
    num = numeric_frame()
    bar = lambda **kw: (lambda raw: raw["plot"].update(type="bar", **kw))
    assert plan_of(num, bar(xColumn="__idx__3"), [S(1)]).axes.x.kind == "category"
    assert plan_of(num, bar(xColumn="__idx__0"), [S(1)]).axes.x.kind == "number"
    assert plan_of(num, bar(), [S(1)]).axes.x.kind == "number"
    assert plan_of(num, bar(xColumn="__idx__0"), [S(1), S(2)]).axes.x.kind == "category"  # 棒の位置に目盛を付ける
    assert plan_of(date_frame(), bar(xColumn="__idx__0"), [S(1)]).axes.x.kind == "category"  # 日時は文字列にして並べる


def test_defaults_plan_is_plain():
    p = plan_of(numeric_frame(), series=[S(1, x="__idx__0")])
    assert p.axes.x == AxisPlan(kind="number") and p.axes.y == AxisPlan(kind="number")
    assert not p.axes.x.customized
    assert dataclasses.replace(p.axes.x, inverted=True).customized


def test_log_axis_ignores_step_and_divisions():
    m = both(axis("y", scale="log", majorStep=0.5, minorTicks="on", minorDivisions=5, tickFormat="sci", tickDecimals=2))
    a = plan_of(numeric_frame(), m, [S(2, x="__idx__0")]).axes.y
    assert a.kind == "log" and a.major_step is None and a.minor == "on" and a.minor_divisions is None
    assert a.tick_format == "sci" and a.tick_decimals == 2


def test_number_axis_keeps_everything():
    m = axis("x", majorStep=0.25, minorTicks="on", minorDivisions=4, tickFormat="fixed", tickDecimals=2, inverted=True)
    a = plan_of(numeric_frame(), m, [S(1, x="__idx__0")]).axes.x
    assert (a.major_step, a.minor, a.minor_divisions, a.tick_format, a.tick_decimals, a.inverted) == (0.25, "on", 4, "fixed", 2, True)


def test_minor_divisions_only_with_minor_on():
    a = plan_of(numeric_frame(), axis("x", minorTicks="auto", minorDivisions=5), [S(1, x="__idx__0")]).axes.x
    assert a.minor_divisions is None
    a = plan_of(numeric_frame(), axis("x", minorTicks="off", minorDivisions=5), [S(1, x="__idx__0")]).axes.x
    assert a.minor_divisions is None


def test_category_axis_ignores_minor_and_format_and_needs_integer_step():
    m = axis("x", minorTicks="on", minorDivisions=3, tickFormat="fixed", majorStep=2)
    a = plan_of(numeric_frame(), m, [S(1, x="__idx__3")]).axes.x
    assert a.kind == "category" and a.minor == "auto" and a.minor_divisions is None and a.tick_format == "auto"
    assert a.major_step == 2 and isinstance(a.major_step, int)
    with pytest.raises(UserError) as e:
        plan_of(numeric_frame(), axis("x", majorStep=1.5), [S(1, x="__idx__3")])
    assert e.value.field == "X軸の主目盛の間隔" and "文字列の列" in e.value.message and "整数" in e.value.message


def test_datetime_axis_applicability():
    m = axis("x", majorStep=3, majorStepUnit="day", tickFormat="sci", dateMin="2026-01-05", dateMax="2026-01-20 12:00")
    a = plan_of(date_frame(), m, [S(1, x="__idx__0")]).axes.x
    assert a.kind == "datetime" and a.major_step == 3 and a.major_step_unit == "day" and a.tick_format == "auto"
    assert a.date_min == "2026-01-05" and a.date_max == "2026-01-20 12:00:00"
    with pytest.raises(UserError) as e:
        plan_of(date_frame(), axis("x", majorStep=2.5), [S(1, x="__idx__0")])
    assert e.value.field == "X軸の主目盛の間隔" and "日時の列" in e.value.message and "整数" in e.value.message


def test_date_range_is_ignored_unless_x_is_datetime():
    a = plan_of(numeric_frame(), axis("x", dateMin="2026-01-05"), [S(1, x="__idx__0")]).axes.x
    assert a.date_min == "" and a.date_max == ""
    a = plan_of(numeric_frame(), axis("x", dateMin="2026-01-05"), [S(1, x="__idx__3")]).axes.x
    assert a.date_min == ""


def test_numeric_range_is_ignored_with_datetime_x():
    """X が日時のとき、数値の範囲の入力欄は隠れているので使わない（エラーにしない）。対数軸は今までどおりエラー。"""
    plan = plan_of(date_frame(), axis("x", min=3, max=300), [S(1, x="__idx__0")])
    assert plan.axes.x.kind == "datetime"
    with pytest.raises(UserError):
        plan_of(date_frame(), axis("x", scale="log"), [S(1, x="__idx__0")])


def test_invalid_date_range_errors_only_with_datetime_x():
    bad = axis("x", dateMin="abc")
    with pytest.raises(UserError) as e:
        plan_of(date_frame(), bad, [S(1, x="__idx__0")])
    assert e.value.field == "X軸の範囲（日時）"
    a = plan_of(numeric_frame(), bad, [S(1, x="__idx__0")]).axes.x  # 隠れているので描画を止めない
    assert a.date_min == "" and a.kind == "number"
    with pytest.raises(UserError) as e:
        plan_of(date_frame(), axis("x", dateMin="2026-01-10", dateMax="2026-01-02"), [S(1, x="__idx__0")])
    assert "最小値 < 最大値" in e.value.message


# ---------------------------------------------------------------- too many ticks


def test_tick_count_boundary_number_axis_with_limits():
    both_ = lambda lo, hi: axis("x", majorStep=1, min=lo, max=hi)
    ok = plan_of(numeric_frame(), both_(0, MAX_MAJOR_TICKS - 1), [S(1, x="__idx__0")])  # 100 本
    assert ok.axes.x.major_step == 1.0
    with pytest.raises(UserError) as e:
        plan_of(numeric_frame(), both_(0, MAX_MAJOR_TICKS), [S(1, x="__idx__0")])  # 101 本
    assert e.value.field == "X軸の主目盛の間隔"
    assert e.value.message == "X軸の主目盛の間隔が小さすぎます（目盛が約101本になります。100本まで）。間隔を大きくするか、空欄（自動）にしてください。"


def test_tick_count_uses_data_range_and_margin():
    # データの範囲 1〜4（幅 3）+ 10% = 3.3。間隔 0.03 → 約 111 本
    with pytest.raises(UserError) as e:
        plan_of(numeric_frame(), axis("y", majorStep=0.03), [S(2, x="__idx__0")])
    assert e.value.field == "Y軸の主目盛の間隔" and "約111本" in e.value.message
    plan_of(numeric_frame(), axis("y", majorStep=0.05), [S(2, x="__idx__0")])  # 約 67 本


def test_tick_count_single_limit_combines_with_data():
    # 上限だけ 10 を指定。データの最小は 1 → 幅 9 * 1.1
    with pytest.raises(UserError):
        plan_of(numeric_frame(), axis("y", majorStep=0.09, max=10), [S(2, x="__idx__0")])
    plan_of(numeric_frame(), axis("y", majorStep=0.2, max=10), [S(2, x="__idx__0")])


def test_tick_count_second_y_uses_secondary_series_only():
    series = [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]
    with pytest.raises(UserError) as e:
        plan_of(numeric_frame(), axis("y2", majorStep=0.03), series)
    assert e.value.field == "第2Y軸の主目盛の間隔" and "第2Y軸の主目盛の間隔が小さすぎます" in e.value.message
    # 第1軸は 0〜1e6。第2軸の細かい間隔は第1軸に影響しない
    plan_of(numeric_frame(), axis("y", majorStep=100000), series)


def test_tick_count_bar_includes_zero():
    # 棒グラフの Y は 0 を含む。値が 100〜103 でも 0〜103 として数える
    df = pd.DataFrame({"c": list("abcd"), "v": [100.0, 101.0, 102.0, 103.0]})
    bar = lambda step: both(lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), axis("y", majorStep=step))
    with pytest.raises(UserError):
        plan_of(df, bar(1), [S(1)])  # 0〜103 → 約 114 本
    plan_of(df, bar(2), [S(1)])


def test_tick_count_datetime_boundaries():
    m = lambda hi: axis("x", majorStep=1, majorStepUnit="day", dateMin="2026-01-01", dateMax=hi)
    plan_of(date_frame(), m("2026-04-10"), [S(1, x="__idx__0")])  # 99 日 → 100 本
    with pytest.raises(UserError) as e:
        plan_of(date_frame(), m("2026-04-11"), [S(1, x="__idx__0")])  # 100 日 → 101 本
    assert e.value.field == "X軸の主目盛の間隔" and "約101本" in e.value.message


def test_tick_count_datetime_units():
    # 30 日のデータ + 10% = 33 日。1 時間おきなら約 793 本、1 か月（30.44 日）おきなら 2 本
    with pytest.raises(UserError):
        plan_of(date_frame(), axis("x", majorStep=1, majorStepUnit="hour"), [S(1, x="__idx__0")])
    plan_of(date_frame(), axis("x", majorStep=1, majorStepUnit="month"), [S(1, x="__idx__0")])
    plan_of(date_frame(), axis("x", majorStep=1, majorStepUnit="year"), [S(1, x="__idx__0")])
    with pytest.raises(UserError):
        plan_of(date_frame(), axis("x", majorStep=1, majorStepUnit="second"), [S(1, x="__idx__0")])


def test_tick_count_category_boundaries():
    def cats(n):
        return pd.DataFrame({"c": [f"c{i}" for i in range(n)], "v": np.arange(n, dtype=float)})

    plan_of(cats(100), axis("x", majorStep=1), [S(1, x="__idx__0")])
    with pytest.raises(UserError) as e:
        plan_of(cats(101), axis("x", majorStep=1), [S(1, x="__idx__0")])
    assert e.value.field == "X軸の主目盛の間隔" and "約101本" in e.value.message
    plan_of(cats(101), axis("x", majorStep=2), [S(1, x="__idx__0")])  # 51 本
    bar = lambda step: both(lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), axis("x", majorStep=step))
    plan_of(cats(100), bar(1), [S(1)])
    with pytest.raises(UserError):
        plan_of(cats(101), bar(1), [S(1)])
    with pytest.raises(UserError):
        plan_of(cats(101), bar(1), [S(1), S(1)])  # 複数系列の棒


def test_no_tick_estimate_without_step_or_on_log():
    plan_of(numeric_frame(), axis("x", majorStep=None), [S(1, x="__idx__0")])
    plan_of(numeric_frame(), axis("y", scale="log", majorStep=1e-9), [S(2, x="__idx__0")])  # 対数軸では間隔を使わない


# ---------------------------------------------------------------- generated code: major ticks and formats


def test_multiple_locator_with_fixed_decimals_has_no_missing_ends_or_float_artefacts(tmp_path):
    m = axis("x", majorStep=0.1, tickFormat="fixed", tickDecimals=1)
    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0")])
    assert "ticker.MultipleLocator(0.1)" in b.script.text and "import matplotlib.ticker as ticker" in b.script.text
    s = b.summary()[0]
    assert s["xmajor"] == "MultipleLocator" and s["xformatter"] == "FormatStrFormatter"
    with b.full() as run:
        labels = [lab for _, lab in visible_labels(run.fig.axes[0])]
    assert labels == ["0.0", "0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0"]
    assert all(re.fullmatch(r"-?\d\.\d", lab) for lab in s["xticklabels"] if lab)


def test_multiple_locator_default_format_labels(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("x", majorStep=0.1), [S(1, x="__idx__0")])
    with b.full() as run:
        labels = [lab for _, lab in visible_labels(run.fig.axes[0])]
    assert labels[0] == "0.0" and labels[3] == "0.3" and labels[-1] == "1.0"


def test_y_major_step(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", majorStep=0.5), [S(2, x="__idx__0")])
    with b.full() as run:
        locs = [loc for loc, _ in visible_labels(run.fig.axes[0], "y")]
    assert np.allclose(np.diff(locs), 0.5) and b.summary()[0]["ymajor"] == "MultipleLocator"


def test_pow10_format_has_offset_text(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", tickFormat="pow10"), [S(1, x="__idx__0")])
    assert "y_formatter = ticker.ScalarFormatter(useMathText=True)" in b.script.text
    assert "y_formatter.set_powerlimits((0, 0))" in b.script.text
    s = b.summary()[0]
    assert s["yformatter"] == "ScalarFormatter" and "10^{6}" in s["yoffset"]


def test_default_has_no_offset_for_small_values(tmp_path):
    assert Built(tmp_path, numeric_frame(), None, [S(2, x="__idx__0")]).summary()[0]["yoffset"] == ""


def test_sci_format_labels(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", tickFormat="sci", tickDecimals=2), [S(1, x="__idx__0")])
    assert 'ticker.FormatStrFormatter("%.2e")' in b.script.text
    labels = [lab for lab in b.summary()[0]["yticklabels"] if lab]
    assert labels and all(re.fullmatch(r"-?\d\.\d\de[+-]\d\d", lab) for lab in labels)


def test_fixed_zero_decimals(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", tickFormat="fixed", tickDecimals=0), [S(2, x="__idx__0")])
    assert 'FormatStrFormatter("%.0f")' in b.script.text
    assert all(re.fullmatch(r"-?\d+", lab) for lab in b.summary()[0]["yticklabels"] if lab)


def test_second_y_axis_ticks(tmp_path):
    def m(raw):
        raw["axes"]["y2"].update(majorStep=1, tickFormat="fixed", tickDecimals=0, inverted=True, minorTicks="off")

    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)])
    assert "ax2.yaxis.set_major_locator(ticker.MultipleLocator(1.0))" in b.script.text
    assert "y2_formatter" not in b.script.text and "ax2.invert_yaxis()" in b.script.text
    s = b.summary()
    assert s[1]["ymajor"] == "MultipleLocator" and s[1]["yinverted"] is True and s[0]["yinverted"] is False
    assert s[1]["yminor"] == "NullLocator"
    assert s[1]["ylim"][0] > s[1]["ylim"][1]


# ---------------------------------------------------------------- minor ticks


def minor_count_inside(ax, which="x"):
    axis_ = ax.xaxis if which == "x" else ax.yaxis
    lo, hi = sorted(ax.get_xlim() if which == "x" else ax.get_ylim())
    majors = axis_.get_majorticklocs()
    return len([m for m in axis_.get_minorticklocs() if lo < m < hi and not np.isclose(majors, m).any()])


def test_auto_minor_locator_divisions(tmp_path):
    m = axis("x", majorStep=2, minorTicks="on", minorDivisions=2, min=0, max=10)
    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0")])
    assert "ax.xaxis.set_minor_locator(ticker.AutoMinorLocator(2))" in b.script.text
    assert b.summary()[0]["xminor"] == "AutoMinorLocator"
    with b.full() as run:
        assert minor_count_inside(run.fig.axes[0]) == 5  # 5 区間 × (2 等分 → 1 本)
    m = axis("x", majorStep=2, minorTicks="on", minorDivisions=4, min=0, max=10)
    with Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0")]).full() as run:
        assert minor_count_inside(run.fig.axes[0]) == 15


def test_minor_on_without_divisions(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", minorTicks="on"), [S(2, x="__idx__0")])
    assert "ax.yaxis.minorticks_on()" in b.script.text
    s = b.summary()[0]
    assert s["yminor"] == "AutoMinorLocator" and s["xminor"] == "NullLocator"


def test_minor_off_wins_over_grid_minor(tmp_path):
    def m(raw):
        raw["plot"]["grid"].update(minor=True)
        raw["axes"]["x"].update(minorTicks="off")

    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0")])
    assert "ax.minorticks_on()" not in b.script.text and "ax.xaxis.minorticks_off()" in b.script.text
    s = b.summary()[0]
    assert s["xminor"] == "NullLocator" and s["yminor"] == "AutoMinorLocator"  # Y は自動 + 副目盛線 → 副目盛あり


def test_minor_locator_is_not_overridden_by_grid_minor(tmp_path):
    def m(raw):
        raw["plot"]["grid"].update(minor=True)
        raw["axes"]["x"].update(minorTicks="on", minorDivisions=2, majorStep=2, min=0, max=10)

    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0")])
    assert "ax.minorticks_on()" not in b.script.text  # 軸ごとの指定を上書きしてしまう
    with b.full() as run:
        assert minor_count_inside(run.fig.axes[0]) == 5  # 2 等分のまま
    assert b.summary()[0]["yminor"] == "AutoMinorLocator"


def test_all_auto_keeps_the_phase4_lines(tmp_path):
    b = Built(tmp_path, numeric_frame(), lambda r: r["plot"]["grid"].update(minor=True), [S(1, x="__idx__0")])
    assert "ax.minorticks_on()" in b.script.text and "xaxis.minorticks" not in b.script.text
    b = Built(tmp_path, numeric_frame(), axis("y", scale="log"), [S(2, x="__idx__0")])
    assert "ax.minorticks_off()  # 対数軸の補助目盛は出さない" in b.script.text


def test_auto_axis_beside_a_custom_axis_follows_grid_minor(tmp_path):
    # X は「表示」、Y は自動（副目盛線なし → 副目盛なし）
    b = Built(tmp_path, numeric_frame(), axis("x", minorTicks="on"), [S(1, x="__idx__0")])
    s = b.summary()[0]
    assert s["xminor"] == "AutoMinorLocator" and s["yminor"] == "NullLocator"
    # 自動の対数軸は、副目盛線がなければ副目盛を消す
    b = Built(tmp_path, numeric_frame(), both(axis("x", minorTicks="on"), axis("y", scale="log")), [S(2, x="__idx__0")])
    assert "ax.yaxis.minorticks_off()" in b.script.text
    assert b.summary()[0]["yminor"] == "NullLocator"


def test_minor_with_secondary_axis(tmp_path):
    def m(raw):
        raw["axes"]["y2"].update(minorTicks="on", minorDivisions=5)
        raw["plot"]["grid"].update(minor=True)

    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)])
    assert "ax2.yaxis.set_minor_locator(ticker.AutoMinorLocator(5))" in b.script.text
    s = b.summary()
    assert s[1]["yminor"] == "AutoMinorLocator" and s[0]["yminor"] == "AutoMinorLocator"


# ---------------------------------------------------------------- invert / spines


def test_inverted_axes(tmp_path):
    def m(raw):
        raw["axes"]["x"].update(inverted=True, min=0, max=1)
        raw["axes"]["y"].update(inverted=True)

    b = Built(tmp_path, numeric_frame(), m, [S(2, x="__idx__0")])
    assert "ax.invert_xaxis()" in b.script.text and "ax.invert_yaxis()" in b.script.text
    s = b.summary()[0]
    assert s["xinverted"] and s["yinverted"] and s["xlim"] == [1.0, 0.0] and s["ylim"][0] > s["ylim"][1]


def test_not_inverted_by_default(tmp_path):
    s = Built(tmp_path, numeric_frame(), None, [S(1, x="__idx__0")]).summary()[0]
    assert not s["xinverted"] and not s["yinverted"] and s["xlim"][0] < s["xlim"][1]


def test_invert_after_scale_and_limits(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", scale="log", inverted=True, min=1, max=100), [S(2, x="__idx__0")])
    text = b.script.text
    assert text.index('set_yscale("log")') < text.index("set_ylim") < text.index("invert_yaxis")
    assert b.summary()[0]["ylim"] == [100.0, 1.0]


def test_spines_top_and_right(tmp_path):
    s = Built(tmp_path, numeric_frame(), None, [S(1, x="__idx__0")]).summary()[0]
    assert s["spines"] == {"top": True, "right": True}
    b = Built(tmp_path, numeric_frame(), lambda r: r["plot"]["spines"].update(top=False, right=False), [S(1, x="__idx__0")])
    assert b.summary()[0]["spines"] == {"top": False, "right": False}
    assert 'ax.spines["top"]' in b.script.text and 'ax.spines["right"]' in b.script.text and "ax2" not in b.script.text


def test_spines_with_secondary_axis(tmp_path):
    series = [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]
    b = Built(tmp_path, numeric_frame(), lambda r: r["plot"]["spines"].update(top=False, right=False), series)
    s = b.summary()
    assert s[0]["spines"]["top"] is False and s[1]["spines"]["top"] is False  # ax2 の上の枠線も消す
    assert s[0]["spines"]["right"] is True and s[1]["spines"]["right"] is True  # 右は第2Y軸の線なので残す
    assert 'ax2.spines["right"]' not in b.script.text and 'ax.spines["right"]' not in b.script.text


# ---------------------------------------------------------------- datetime ticks and range


@pytest.mark.parametrize(
    "unit,locator,kwarg,frame",
    [
        ("year", "YearLocator", "base", date_frame(2000, "D")),
        ("month", "MonthLocator", "interval", date_frame(400, "D")),
        ("day", "DayLocator", "interval", date_frame(60, "D")),
        ("hour", "HourLocator", "interval", date_frame(96, "h")),
        ("minute", "MinuteLocator", "interval", date_frame(300, "min")),
        ("second", "SecondLocator", "interval", date_frame(200, "s")),
    ],
)
def test_date_unit_locators(tmp_path, unit, locator, kwarg, frame):
    m = axis("x", majorStep=5, majorStepUnit=unit)
    b = Built(tmp_path, frame, m, [S(1, x="__idx__0")])
    assert f"date_locator = mdates.{locator}({kwarg}=5)" in b.script.text
    assert "ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(date_locator))" in b.script.text
    s = b.summary()[0]
    assert s["xmajor"] == locator and s["xformatter"] == "ConciseDateFormatter"


def test_date_day_step_spacing(tmp_path):
    b = Built(tmp_path, date_frame(60), axis("x", majorStep=5, majorStepUnit="day"), [S(1, x="__idx__0")])
    with b.full() as run:
        locs = [loc for loc, _ in visible_labels(run.fig.axes[0])]
    assert np.allclose(np.diff(locs), 5.0)


def test_date_step_with_date_format(tmp_path):
    m = axis("x", majorStep=7, majorStepUnit="day", dateFormat="%m/%d")
    b = Built(tmp_path, date_frame(60), m, [S(1, x="__idx__0")])
    assert 'mdates.DateFormatter("%m/%d")' in b.script.text and "ConciseDateFormatter" not in b.script.text
    s = b.summary()[0]
    assert s["xformatter"] == "DateFormatter" and all(re.fullmatch(r"\d\d/\d\d", lab) for lab in s["xticklabels"] if lab)


def test_date_default_lines_are_unchanged_without_step(tmp_path):
    text = Built(tmp_path, date_frame(60), None, [S(1, x="__idx__0")]).script.text
    assert "date_locator = mdates.AutoDateLocator()" in text and "ticker" not in text


def test_date_range_sets_xlim(tmp_path):
    import matplotlib.dates as mdates

    m = axis("x", dateMin="2026-01-05", dateMax="2026-01-20 12:00")
    b = Built(tmp_path, date_frame(60), m, [S(1, x="__idx__0")])
    assert 'ax.set_xlim(left=pd.Timestamp("2026-01-05"), right=pd.Timestamp("2026-01-20 12:00:00"))' in b.script.text
    lim = b.summary()[0]["xlim"]
    assert lim == [float(mdates.date2num(np.datetime64("2026-01-05"))), float(mdates.date2num(np.datetime64("2026-01-20T12:00:00")))]


def test_date_range_one_side(tmp_path):
    b = Built(tmp_path, date_frame(60), axis("x", dateMax="2026-01-20"), [S(1, x="__idx__0")])
    assert 'ax.set_xlim(right=pd.Timestamp("2026-01-20"))' in b.script.text
    lim = b.summary()[0]["xlim"]
    assert lim[1] == float(__import__("matplotlib.dates", fromlist=["date2num"]).date2num(np.datetime64("2026-01-20")))
    assert lim[0] < lim[1]


def test_date_range_and_invert(tmp_path):
    m = axis("x", dateMin="2026-01-05", dateMax="2026-01-20", inverted=True)
    s = Built(tmp_path, date_frame(60), m, [S(1, x="__idx__0")]).summary()[0]
    assert s["xinverted"] and s["xlim"][0] > s["xlim"][1]


def test_date_range_ignored_for_numeric_x(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("x", dateMin="2026-01-05"), [S(1, x="__idx__0")])
    assert "Timestamp" not in b.script.text and "set_xlim" not in b.script.text


# ---------------------------------------------------------------- category ticks


def test_category_line_stride(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(6)], "v": np.arange(6.0)})
    b = Built(tmp_path, df, axis("x", majorStep=2), [S(1, x="__idx__0")])
    assert "ax.xaxis.set_major_locator(ticker.MultipleLocator(2))" in b.script.text and "MaxNLocator" not in b.script.text
    s = b.summary()[0]
    assert s["xmajor"] == "MultipleLocator"
    with b.full() as run:
        assert [lab for loc, lab in visible_labels(run.fig.axes[0])] == ["c0", "c2", "c4"]


def test_category_stride_replaces_thinning(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(40)], "v": np.arange(40.0)})
    auto = Built(tmp_path, df, None, [S(1, x="__idx__0")])
    assert "ticker.MaxNLocator(nbins=25, integer=True)" in auto.script.text  # Phase 4 の間引き
    assert auto.summary()[0]["xmajor"] == "MaxNLocator"
    b = Built(tmp_path, df, axis("x", majorStep=10), [S(1, x="__idx__0")])
    assert "MaxNLocator" not in b.script.text and b.summary()[0]["xmajor"] == "MultipleLocator"


def test_category_scatter_stride(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(8)], "v": np.arange(8.0)})
    b = Built(tmp_path, df, both(lambda r: r["plot"].update(type="scatter"), axis("x", majorStep=3)), [S(1, x="__idx__0")])
    assert b.summary()[0]["xmajor"] == "MultipleLocator"


def test_multi_bar_tick_step(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(6)], "a": np.arange(6.0), "b": np.arange(6.0) + 1})
    m = both(lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), axis("x", majorStep=2))
    b = Built(tmp_path, df, m, [S(1), S(2)])
    assert "tick_step = 2\n" in b.script.text and "max(1, len(positions) // 25)" not in b.script.text
    assert [lab for lab in b.summary()[0]["xticklabels"] if lab] == ["c0", "c2", "c4"]
    auto = Built(tmp_path, df, lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), [S(1), S(2)])
    assert "tick_step = max(1, len(positions) // 25)" in auto.script.text


def test_single_bar_text_x_stride(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(6)], "a": np.arange(6.0)})
    m = both(lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), axis("x", majorStep=2))
    b = Built(tmp_path, df, m, [S(1)])
    assert "ticker.MultipleLocator(2)" in b.script.text
    with b.full() as run:
        assert [lab for loc, lab in visible_labels(run.fig.axes[0])] == ["c0", "c2", "c4"]


def test_bar_numeric_x_uses_number_locator(tmp_path):
    m = both(lambda r: r["plot"].update(type="bar", xColumn="__idx__0"), axis("x", majorStep=0.5))
    b = Built(tmp_path, numeric_frame(), m, [S(2)])
    assert "ticker.MultipleLocator(0.5)" in b.script.text and b.summary()[0]["xmajor"] == "MultipleLocator"


def test_category_minor_and_format_are_ignored_in_code(tmp_path):
    df = pd.DataFrame({"c": [f"c{i}" for i in range(6)], "v": np.arange(6.0)})
    b = Built(tmp_path, df, axis("x", minorTicks="on", tickFormat="sci"), [S(1, x="__idx__0")])
    assert "xaxis.minorticks" not in b.script.text and "FormatStrFormatter" not in b.script.text


# ---------------------------------------------------------------- log axes


def test_log_axis_ignores_step_in_code(tmp_path):
    b = Built(tmp_path, numeric_frame(), axis("y", scale="log", majorStep=0.5), [S(2, x="__idx__0")])
    assert "MultipleLocator" not in b.script.text and "ticker" not in b.script.text
    assert b.summary()[0]["ymajor"] == "LogLocator"


@pytest.mark.parametrize(
    "fmt,expected_formatter,needle",
    [
        ("fixed", "FormatStrFormatter", 'ticker.FormatStrFormatter("%.1f")'),
        ("sci", "FormatStrFormatter", 'ticker.FormatStrFormatter("%.1e")'),
        ("pow10", "LogFormatterSciNotation", "ticker.LogFormatterSciNotation()"),
    ],
)
def test_log_axis_formats(tmp_path, fmt, expected_formatter, needle):
    b = Built(tmp_path, numeric_frame(), axis("y", scale="log", tickFormat=fmt), [S(2, x="__idx__0")])
    assert needle in b.script.text and "y.set_minor_formatter" not in b.script.text
    assert "ax.yaxis.set_minor_formatter(ticker.NullFormatter())" in b.script.text
    assert b.summary()[0]["yformatter"] == expected_formatter


def test_log_axis_minor_on_uses_standard_log_minor_ticks(tmp_path):
    b = Built(tmp_path, numeric_frame(), both(axis("y", scale="log", minorTicks="on", minorDivisions=5)), [S(2, x="__idx__0")])
    assert "AutoMinorLocator" not in b.script.text and "ax.yaxis.minorticks_on()" in b.script.text
    assert b.summary()[0]["yminor"] == "LogLocator"


# ---------------------------------------------------------------- misc


def test_ticker_import_only_when_needed(tmp_path):
    n = numeric_frame()
    assert "ticker" not in Built(tmp_path, n, None, [S(1, x="__idx__0")]).script.text
    assert "ticker" not in Built(tmp_path, n, axis("x", inverted=True, minorTicks="on"), [S(1, x="__idx__0")]).script.text
    assert "import matplotlib.ticker as ticker" in Built(tmp_path, n, axis("x", majorStep=0.5), [S(1, x="__idx__0")]).script.text
    assert "import matplotlib.ticker as ticker" in Built(tmp_path, n, axis("x", minorTicks="on", minorDivisions=3), [S(1, x="__idx__0")]).script.text


def test_tick_steps_cover_the_tick_lines(tmp_path):
    b = Built(tmp_path, numeric_frame(), both(axis("x", majorStep=0.5, inverted=True), axis("y", min=0, max=2000)), [S(1, x="__idx__0")])
    msgs = {(s.message, s.field) for s in b.script.steps}
    assert (codegen.tick_error_message("X"), "X軸の目盛") in msgs
    assert (codegen.axis_error_message("Y"), "Y軸の範囲") in msgs
    step = next(s for s in b.script.steps if s.field == "X軸の目盛")
    lines = b.script.text.split("\n")[step.start - 1 : step.end]
    assert any("MultipleLocator" in ln for ln in lines) and any("invert_xaxis" in ln for ln in lines)


def test_all_features_together_agree(tmp_path):
    def m(raw):
        raw["plot"]["grid"].update(major=True, minor=True)
        raw["plot"]["spines"].update(top=False, right=False)
        raw["axes"]["x"].update(majorStep=0.25, minorTicks="on", minorDivisions=5, tickFormat="fixed", tickDecimals=2, inverted=True)
        raw["axes"]["y"].update(tickFormat="pow10", minorTicks="off")
        raw["axes"]["y2"].update(majorStep=1, tickFormat="sci", tickDecimals=1, inverted=True)

    b = Built(tmp_path, numeric_frame(), m, [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)])
    compile(b.script.text, "plot.py", "exec")
    b.summary()
    assert b.script.auto_render_text().count("\n") == b.script.text.count("\n")


# ---------------------------------------------------------------- injection


HOSTILE_DATES = ['2026-01-01"); import os; os.system("x"); ("', "2026-01-01\nimport os", "'''", "\\"]


@pytest.mark.parametrize("hostile", HOSTILE_DATES)
def test_hostile_date_range_is_rejected_by_dataprep_for_datetime_x(hostile):
    with pytest.raises(UserError) as e:
        plan_of(date_frame(), axis("x", dateMin=hostile), [S(1, x="__idx__0")])
    assert e.value.field == "X軸の範囲（日時）"


@pytest.mark.parametrize("hostile", HOSTILE_DATES)
def test_hostile_plan_values_only_appear_as_literals_and_comments(tmp_path, hostile):
    """AxisPlan に（設定の検証を通らない）悪意のある文字列が入っても、literal() / comment_text() の外には出ない。"""
    b = Built(tmp_path, date_frame(30), None, [S(1, x="__idx__0")])
    x = dataclasses.replace(b.plan.axes.x, date_min=hostile, date_max=hostile, major_step=2, major_step_unit="day")
    plan = dataclasses.replace(b.plan, axes=AxesPlan(x=x, y=b.plan.axes.y))
    text = generate_script(b.settings, b.loaded.source, plan).text
    tree = ast.parse(text)
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert not ({"system", "__import__", "exit", "eval", "exec", "open"} & calls)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import) and any(a.name == "os" for a in n.names)]
    for line in text.split("\n"):
        assert "\r" not in line and "\x0b" not in line and "\x85" not in line
    stamps = [n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "Timestamp"]
    assert stamps == [hostile, hostile]  # 文字列定数として、そのまま（実行されない形で）入る


def test_literal_is_the_only_way_values_reach_the_tick_lines():
    # 目盛の行は literal() だけを通す。str / int / 有限の float / bool / None 以外は書き出せない
    for bad in (float("nan"), float("inf"), [1], (1,), {"a": 1}, object()):
        with pytest.raises((TypeError, ValueError)):
            codegen.literal(bad)
