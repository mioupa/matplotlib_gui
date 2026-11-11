"""Phase 5a: エラーバー（G1）。dataprep の ErrorPlan・警告・目盛の見積もりと、生成コードを CPython で実行した図を検査する。"""
import contextlib
import re

import numpy as np
import pandas as pd
import pytest

from mplgui.codegen import ERROR_BAR_FUNCTION, comment_text, generate_script, literal
from mplgui.dataprep import ErrorPlan, plan_plot
from mplgui.errors import UserError
from mplgui.loader import load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit

N = 8


def frame():
    t = np.arange(N, dtype=float)
    return pd.DataFrame(
        {
            "t": t,  # 0
            "v": t * 2 + 10,  # 1
            "e": np.full(N, 0.5),  # 2
            "e2": np.full(N, 1.5),  # 3
            "xe": np.full(N, 0.25),  # 4
            "w": t + 100,  # 5
            "we": np.full(N, 2.0),  # 6
        }
    )


def ES(mode="column", symmetric=True, **kw):
    return {"mode": mode, "symmetric": symmetric, **kw}


def EB(y=None, x=None, cap=None):
    d = {}
    if y is not None:
        d["y"] = y
    if x is not None:
        d["x"] = x
    if cap is not None:
        d["capSize"] = cap
    return d


def series(y=1, x="", eb=None, **kw):
    d = {"x": x if isinstance(x, str) else f"__idx__{x}", "y": f"__idx__{y}"}
    if eb is not None:
        d["errorBars"] = eb
    d.update(kw)
    return d


def raw_settings(series_list, plot_type="line", mutate=None):
    raw = default_settings()
    raw["series"] = series_list
    raw["plot"]["type"] = plot_type
    if mutate:
        mutate(raw)
    return raw


class Built:
    def __init__(self, tmp_path, df, series_list, plot_type="line", mutate=None):
        self.dir = tmp_path
        df.to_csv(tmp_path / "d.csv", index=False, encoding="utf-8")
        self.loaded = load_file((tmp_path / "d.csv").read_bytes(), "d.csv", "", True)
        self.settings = parse_settings(raw_settings(series_list, plot_type, mutate))
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

    def check(self, fn):
        """全体の実行と自動描画用の実行の両方に fn(fig) を適用し、要約が一致することも確かめる。"""
        with self.full() as run:
            fn(run.fig)
            full = figure_summary(run.fig)
        with self.auto() as run:
            fn(run.fig)
            auto = figure_summary(run.fig)
        assert full == auto
        return full


def bars_of(ax):
    return [ln for ln in ax.lines if ln.get_label() == "_errorbar"]


def stems(ax, direction="y"):
    """区切りの NaN を含む1本の線 → (固定側の値, 下端, 上端) の配列。"""
    line = bars_of(ax)[0]
    fixed, ends = (line.get_xdata(), line.get_ydata()) if direction == "y" else (line.get_ydata(), line.get_xdata())
    ends = np.asarray(ends, dtype=float).reshape(-1, 3)
    return np.asarray(fixed)[::3], ends[:, 0], ends[:, 1]


def build(tmp_path, df=None, **kw):
    s = kw.pop("series")
    return Built(tmp_path, df if df is not None else frame(), s, **kw)


# ---------------------------------------------------------------- 描画計画


def plan_of(series_list, df=None, plot_type="line", mutate=None):
    loaded = load_file((df if df is not None else frame()).to_csv(index=False).encode("utf-8"), "d.csv", "", True)
    settings = parse_settings(raw_settings(series_list, plot_type, mutate))
    return plan_plot(loaded.df, settings)


def test_plan_without_error_bars_has_none():
    p = plan_of([series()]).series[0]
    assert p.y_err is None and p.x_err is None and p.cap_size == 3.0


def test_plan_column_symmetric():
    p = plan_of([series(eb=EB(y=ES(column="__idx__2"), cap=5))]).series[0]
    assert p.y_err == ErrorPlan("y", "column", True, index=2, label="e [2]")
    assert p.x_err is None and p.cap_size == 5.0


def test_plan_column_asymmetric_and_x():
    p = plan_of([series(x=0, eb=EB(y=ES(symmetric=False, column="__idx__2", columnMinus="__idx__3"), x=ES(column="__idx__4")))]).series[0]
    assert (p.y_err.index, p.y_err.index_minus, p.y_err.label, p.y_err.label_minus) == (2, 3, "e [2]", "e2 [3]")
    assert p.x_err.direction == "x" and p.x_err.index == 4


def test_plan_fixed():
    p = plan_of([series(eb=EB(y=ES("fixed", symmetric=False, value=0.5, valueMinus=0.25)))]).series[0]
    assert (p.y_err.mode, p.y_err.value, p.y_err.value_minus, p.y_err.symmetric) == ("fixed", 0.5, 0.25, False)
    p = plan_of([series(eb=EB(y=ES("fixed", value=2)))]).series[0]
    assert p.y_err.value == 2 and p.y_err.value_minus is None


def test_plan_column_is_resolved_after_skip_rows_in_the_series_own_source():
    df1 = frame()
    df2 = frame().assign(e=np.arange(N) + 1.0)
    raw = raw_settings([series(eb=EB(y=ES(column="__idx__2"))), series(eb=EB(y=ES(column="__idx__2")), source="d2")])
    raw["load"]["files"] = [{"id": "d1", "name": "a.csv", "sheet": ""}, {"id": "d2", "name": "b.csv", "sheet": ""}]
    raw["plot"]["skipRows"] = 2
    a = load_file(df1.to_csv(index=False).encode(), "a.csv", "", True)
    b = load_file(df2.to_csv(index=False).encode(), "b.csv", "", True)
    plan = plan_plot({"d1": a.df, "d2": b.df}, parse_settings(raw))
    assert [p.data_var for p in plan.series] == ["df1", "df2"]
    assert plan.series[1].y_err.label == "e [2]"
    script = generate_script(parse_settings(raw), {"d1": a.source, "d2": b.source}, plan)
    assert 'y_err = pd.to_numeric(df1.iloc[:, 2]' in script.text and 'y_err = pd.to_numeric(df2.iloc[:, 2]' in script.text


def test_plan_error_column_out_of_range():
    with pytest.raises(UserError) as e:
        plan_of([series(eb=EB(y=ES(column="__idx__9")))])
    assert e.value.field == "系列1のY誤差の列" and "10列目" in str(e.value)
    with pytest.raises(UserError) as e:
        plan_of([series(), series(x=0, eb=EB(x=ES(column="__idx__9")))])
    assert e.value.field == "系列2のX誤差の列"
    with pytest.raises(UserError) as e:
        plan_of([series(eb=EB(y=ES(symmetric=False, column="__idx__2", columnMinus="__idx__9")))])
    assert e.value.field == "系列1のY誤差の列"


def test_plan_x_error_with_datetime_or_text_x():
    df = frame().assign(日時=pd.date_range("2026-01-01", periods=N).strftime("%Y-%m-%d"), 区分=[f"区分{i}" for i in range(N)])
    with pytest.raises(UserError) as e:
        plan_of([series(x=7, eb=EB(x=ES("fixed", value=1)))], df)
    assert str(e.value) == "系列1: X が日時の列のときは、X方向のエラーバーは付けられません。" and e.value.field == "系列1のX誤差の方式"
    with pytest.raises(UserError) as e:
        plan_of([series(x=8, eb=EB(x=ES("fixed", value=1)))], df)
    assert str(e.value) == "系列1: X が文字列の列のときは、X方向のエラーバーは付けられません。"
    # Y 方向は付けられる
    assert plan_of([series(x=7, eb=EB(y=ES("fixed", value=1)))], df).series[0].y_err is not None
    assert plan_of([series(x=8, eb=EB(y=ES("fixed", value=1)))], df).series[0].y_err is not None


def test_plan_bar_ignores_x_error_and_keeps_y():
    p = plan_of([series(eb=EB(y=ES("fixed", value=1), x=ES("fixed", value=1)))], plot_type="bar").series[0]
    assert p.y_err is not None and p.x_err is None


def test_plan_series_without_points_has_no_error_plan():
    df = frame().assign(空=[np.nan] * N)
    plan = plan_of([series(), series(y=7, eb=EB(y=ES("fixed", value=1)))], df.rename(columns={"空": "空"}))
    assert plan.series[1].has_points is False and plan.series[1].y_err is None


# ---------------------------------------------------------------- 警告


def warn_texts(plan):
    return [w["message"] for w in plan.warnings]


def test_warning_non_numeric_negative_blank_and_only_plotted_rows():
    df = frame().astype({"e": object})
    df.loc[1, "e"] = "abc"  # 数値にできない
    df.loc[2, "e"] = "-3"  # 負
    df.loc[3, "e"] = ""  # 空欄は警告しない
    df.loc[4, "e"] = "-1"  # この行は Y が欠けていて描かない → 数えない
    df.loc[4, "v"] = np.nan
    df.loc[5, "e"] = "zzz"  # 描かない行
    df.loc[5, "t"] = np.nan
    plan = plan_of([series(x=0, eb=EB(y=ES(column="__idx__2")))], df)
    msgs = warn_texts(plan)
    assert len(msgs) == 2
    assert msgs[0] == '系列1: Y誤差の列「e」[2] に数値にできない値が1件あったため、その点のエラーバーは描きません（例: "abc"）。'
    assert msgs[1] == '系列1: Y誤差の列「e」[2] に負の値が1件あったため、その点のエラーバーは描きません（例: "-3"）。'
    assert all(w["series"] == 1 for w in plan.warnings)


def test_warning_examples_are_limited_to_three_and_unique():
    df = frame().astype({"e": object})
    for i, v in enumerate(["a", "b", "c", "d", "a"]):
        df.loc[i, "e"] = v
    msgs = warn_texts(plan_of([series(eb=EB(y=ES(column="__idx__2")))], df))
    assert '5件' in msgs[0] and '"a", "b", "c"' in msgs[0] and '"d"' not in msgs[0]


def test_warning_has_load_hint_for_thousands_and_decimal():
    df = frame().astype({"e": object})
    df.loc[0, "e"] = "1,234"
    assert "桁区切り" in warn_texts(plan_of([series(eb=EB(y=ES(column="__idx__2")))], df))[0]
    df.loc[0, "e"] = "1,5"
    assert "小数点" in warn_texts(plan_of([series(eb=EB(y=ES(column="__idx__2")))], df))[0]


def test_warning_asymmetric_names_each_side_and_x_error():
    df = frame().astype({"e": object, "xe": object})
    df.loc[0, "e"] = "x"
    df.loc[1, "e2"] = -1.0
    df.loc[2, "xe"] = "q"
    plan = plan_of(
        [series(x=0, eb=EB(y=ES(symmetric=False, column="__idx__2", columnMinus="__idx__3"), x=ES(column="__idx__4")))], df
    )
    msgs = warn_texts(plan)
    assert any("Y誤差（上）の列「e」[2]" in m for m in msgs)
    assert any("Y誤差（下）の列「e2」[3]" in m and "負の値" in m for m in msgs)
    assert any("X誤差の列「xe」[4]" in m for m in msgs)


def test_warning_bar_counts_only_bar_rows():
    df = frame().astype({"e": object})
    df.loc[1, "e"] = "bad"
    df.loc[2, "e"] = "bad"
    df.loc[2, "v"] = np.nan  # 棒を描かない行
    msgs = warn_texts(plan_of([series(eb=EB(y=ES(column="__idx__2")))], df, plot_type="bar"))
    assert len(msgs) == 1 and "1件" in msgs[0]


# ---------------------------------------------------------------- 目盛の見積もり


def test_tick_estimate_includes_error_bar_ends():
    def step(raw):
        raw["axes"]["y"]["majorStep"] = 1  # データ 10〜24 → 約 16 本

    def tall(e):
        return [series(eb=EB(y=ES("fixed", value=e)))]

    plan_of(tall(0), mutate=step)  # エラーバー無しと同じ範囲
    plan_of(tall(1), mutate=step)
    with pytest.raises(UserError) as e:
        plan_of(tall(100), mutate=step)  # 範囲が約 200 → 約 220 本
    assert e.value.field == "Y軸の主目盛の間隔"


def test_tick_estimate_includes_x_error_and_second_axis():
    def stepx(raw):
        raw["axes"]["x"]["majorStep"] = 1

    with pytest.raises(UserError) as e:
        plan_of([series(x=0, eb=EB(x=ES("fixed", value=500)))], mutate=stepx)
    assert e.value.field == "X軸の主目盛の間隔"

    def step2(raw):
        raw["axes"]["y2"]["majorStep"] = 1

    plan_of([series(), series(y=5, secondary_axis=False)], mutate=step2)
    with pytest.raises(UserError) as e:
        plan_of([series(), series(y=5, secondaryAxis=True, eb=EB(y=ES("fixed", value=500)))], mutate=step2)
    assert e.value.field == "第2Y軸の主目盛の間隔"


def test_tick_estimate_bar_includes_error_ends():
    def step(raw):
        raw["axes"]["y"]["majorStep"] = 1

    plan_of([series(eb=EB(y=ES("fixed", value=1)))], plot_type="bar", mutate=step)
    with pytest.raises(UserError):
        plan_of([series(eb=EB(y=ES("fixed", value=500)))], plot_type="bar", mutate=step)


# ---------------------------------------------------------------- 生成コード（line / scatter）


def test_no_error_bars_means_no_helper():
    script = generate_script(
        parse_settings(raw_settings([series()])),
        load_file(frame().to_csv(index=False).encode(), "d.csv", "", True).source,
        plan_of([series()]),
    )
    assert "draw_error_bars" not in script.text and "_err" not in script.text


def test_line_column_symmetric_geometry_and_text(tmp_path):
    b = build(tmp_path, series=[series(eb=EB(y=ES(column="__idx__2")))])
    text = b.script.text
    assert text.count("def draw_error_bars(") == 1
    assert text.index("def draw_error_bars") < text.index("# ==== 1. データの読み込み ====") and text.index("FONT_SIZE =") < text.index("def draw_error_bars")
    assert 'y_err = y_err.where(y_err >= 0)' in text
    assert "draw_error_bars(ax, x[ok], y[ok], y[ok] - y_err[ok], y[ok] + y_err[ok], direction=\"y\"" in text

    def geom(fig):
        ax = fig.axes[0]
        xs, lo, hi = stems(ax)
        df = frame()
        assert np.allclose(xs, df["t"]) and np.allclose(lo, df["v"] - 0.5) and np.allclose(hi, df["v"] + 0.5)
        (line,) = bars_of(ax)  # 線1本。両端の短い線はその端点の記号
        assert line.get_marker() == "_" and line.get_markersize() == 6.0
        assert ax.get_ylim()[0] < 9.5 and ax.get_ylim()[1] > 24.5  # エラーバーの端も範囲に入る
        assert len(ax.get_legend().get_texts()) == 1  # 系列だけ。エラーバーは凡例に出ない

    summary = b.check(geom)
    assert summary[0]["errorbars"] == 1


def test_cap_size_zero_has_no_caps(tmp_path):
    b = build(tmp_path, series=[series(eb=EB(y=ES("fixed", value=1), cap=0))])
    with b.full() as run:
        (line,) = bars_of(run.fig.axes[0])  # 縦線だけ
        assert line.get_marker() == "None"


def test_geometry_matches_axes_errorbar(tmp_path):
    b = build(tmp_path, series=[series(color="#0072B2", lineWidth=3, eb=EB(y=ES(column="__idx__2"), cap=4))])
    df = frame()
    with b.full() as run:
        ax = run.fig.axes[0]
        xs, lo, hi = stems(ax)
        (cap,) = bars_of(ax)
        assert cap.get_marker() == "_" and cap.get_markersize() == 8.0 and cap.get_markeredgewidth() == 3
        ref_fig = run.fig.__class__()
        ref = ref_fig.subplots()
        ref.errorbar(df["t"], df["v"], yerr=0.5, fmt="none", capsize=4, capthick=3, elinewidth=3, color="#0072B2")
        seg = np.asarray(ref.collections[0].get_segments())
        assert np.allclose(seg[:, 0, 1], lo) and np.allclose(seg[:, 1, 1], hi)
        assert bars_of(ax)[0].get_color() == "#0072B2" and bars_of(ax)[0].get_linewidth() == 3


def test_asymmetric_column_and_fixed(tmp_path):
    b = build(tmp_path, series=[series(eb=EB(y=ES(symmetric=False, column="__idx__2", columnMinus="__idx__3")))])
    assert "y_err_plus" in b.script.text and "y_err_minus" in b.script.text
    df = frame()

    def geom(fig):
        _, lo, hi = stems(fig.axes[0])
        assert np.allclose(lo, df["v"] - 1.5) and np.allclose(hi, df["v"] + 0.5)

    b.check(geom)
    b = build(tmp_path, series=[series(eb=EB(y=ES("fixed", symmetric=False, value=0.5, valueMinus=0.25)))])
    assert "y[ok] - 0.25, y[ok] + 0.5" in b.script.text

    def geom2(fig):
        _, lo, hi = stems(fig.axes[0])
        assert np.allclose(lo, df["v"] - 0.25) and np.allclose(hi, df["v"] + 0.5)

    b.check(geom2)


def test_nan_gaps_for_blank_negative_and_non_numeric(tmp_path):
    df = frame().astype({"e": object})
    df.loc[1, "e"] = ""
    df.loc[2, "e"] = "-1"
    df.loc[3, "e"] = "abc"
    b = build(tmp_path, df, series=[series(eb=EB(y=ES(column="__idx__2")))])

    def geom(fig):
        ax = fig.axes[0]
        _, lo, hi = stems(ax)
        assert np.isnan(lo[[1, 2, 3]]).all() or np.isnan(hi[[1, 2, 3]]).all()
        good = [0, 4, 5, 6, 7]
        assert np.allclose(lo[good], frame()["v"][good] - 0.5)
        assert not np.isnan(lo[good]).any()

    b.check(geom)
    assert len(b.plan.warnings) == 2


def test_rows_not_plotted_have_no_error_bars(tmp_path):
    df = frame()
    df.loc[3, "v"] = np.nan
    b = build(tmp_path, df, series=[series(eb=EB(y=ES(column="__idx__2")))])

    def geom(fig):
        xs, _, _ = stems(fig.axes[0])
        assert len(xs) == N - 1 and 3.0 not in xs

    b.check(geom)


def test_scatter_zorder_and_x_errors(tmp_path):
    b = build(tmp_path, series=[series(x=0, eb=EB(y=ES("fixed", value=1), x=ES(column="__idx__4")))], plot_type="scatter")
    assert b.script.text.count("zorder=1") == 2

    def geom(fig):
        ax = fig.axes[0]
        assert all(ln.get_zorder() == 1 for ln in bars_of(ax))
        assert ax.collections[0].get_zorder() == 1
        assert len(bars_of(ax)) == 2  # Y・X それぞれ線1本（両端は記号）
        stem_x = [ln for ln in bars_of(ax) if ln.get_marker() == "|"]
        assert [ln.get_marker() for ln in bars_of(ax)] == ["_", "|"]
        xs = np.asarray(stem_x[0].get_xdata(), dtype=float).reshape(-1, 3)
        assert np.allclose(xs[:, 0], frame()["t"] - 0.25) and np.allclose(xs[:, 1], frame()["t"] + 0.25)

    b.check(geom)


def test_series_on_secondary_axis_draws_on_ax2(tmp_path):
    b = build(tmp_path, series=[series(), series(y=5, secondaryAxis=True, eb=EB(y=ES(column="__idx__6")))])
    assert "draw_error_bars(ax2," in b.script.text

    def geom(fig):
        ax, ax2 = fig.axes
        assert not bars_of(ax) and len(bars_of(ax2)) == 1
        assert ax2.get_ylim()[1] > 100 + N - 1 + 2

    summary = b.check(geom)
    assert [s["errorbars"] for s in summary] == [0, 1]


def test_datetime_x_with_y_errors(tmp_path):
    df = frame().assign(日時=pd.date_range("2026-01-01", periods=N).strftime("%Y-%m-%d"))
    b = build(tmp_path, df, series=[series(x=7, eb=EB(y=ES(column="__idx__2")))])

    def geom(fig):
        ax = fig.axes[0]
        xs, lo, hi = stems(ax)
        assert np.allclose(hi - lo, 1.0) and len(xs) == N
        assert type(ax.xaxis.get_converter()).__name__ .endswith("DateConverter")

    b.check(geom)


def test_text_x_with_y_errors(tmp_path):
    df = frame().assign(区分=[f"区分{i}" for i in range(N)])
    b = build(tmp_path, df, series=[series(x=7, eb=EB(y=ES("fixed", value=1)))])

    def geom(fig):
        ax = fig.axes[0]
        line = bars_of(ax)[0]
        assert list(dict.fromkeys(line.get_xdata().tolist())) == [f"区分{i}" for i in range(N)]
        assert [t.get_text() for t in ax.get_xticklabels()][:3] == ["区分0", "区分1", "区分2"]

    b.check(geom)


def test_log_y_with_lower_end_not_positive(tmp_path):
    b = build(
        tmp_path,
        series=[series(eb=EB(y=ES("fixed", value=15)))],
        mutate=lambda raw: raw["axes"]["y"].update(scale="log"),
    )

    def geom(fig):
        ax = fig.axes[0]
        assert ax.get_yscale() == "log" and ax.get_ylim()[0] > 0

    b.check(geom)


def test_legend_has_no_error_bar_entries(tmp_path):
    b = build(
        tmp_path,
        series=[series(label="温度", eb=EB(y=ES("fixed", value=1))), series(y=5, label="圧力", eb=EB(y=ES("fixed", value=1)))],
        mutate=lambda raw: raw["plot"].update(legend="best"),
    )
    summary = b.check(lambda fig: None)
    assert summary[0]["legend"] == ["温度", "圧力"]


# ---------------------------------------------------------------- 生成コード（bar）


def test_bar_single_series_yerr_forms(tmp_path):
    df = frame()
    cases = [
        (ES(column="__idx__2"), "yerr=y_err[ok]", lambda e: np.allclose(e, [[0.5] * N, [0.5] * N])),
        (ES(symmetric=False, column="__idx__2", columnMinus="__idx__3"), "yerr=[y_err_minus[ok], y_err_plus[ok]]", lambda e: np.allclose(e, [[1.5] * N, [0.5] * N])),
        (ES("fixed", value=2), "yerr=2.0", lambda e: np.allclose(e, [[2] * N, [2] * N])),
        (ES("fixed", symmetric=False, value=2, valueMinus=1), "yerr=[[1.0], [2.0]]", lambda e: np.allclose(e, [[1] * N, [2] * N])),
    ]
    for spec, expr, check in cases:
        b = build(tmp_path, df, series=[series(eb=EB(y=spec, cap=5))], plot_type="bar")
        assert expr in b.script.text and 'ecolor="black"' in b.script.text and "capsize=5.0" in b.script.text

        def geom(fig, check=check):
            ax = fig.axes[0]
            err = [c for c in ax.containers if type(c).__name__ == "ErrorbarContainer"][0]
            seg = np.asarray(err.lines[2][0].get_segments())
            heights = df["v"].to_numpy()
            low, high = heights - seg[:, 0, 1], seg[:, 1, 1] - heights
            assert check(np.vstack([low, high]))

        summary = b.check(geom)
        assert summary[0]["errorbars"] == 1


def test_bar_blank_and_negative_are_not_drawn(tmp_path):
    df = frame().astype({"e": object})
    df.loc[0, "e"] = ""
    df.loc[1, "e"] = "-2"
    b = build(tmp_path, df, series=[series(eb=EB(y=ES(column="__idx__2")))], plot_type="bar")
    with b.full() as run:
        cont = [c for c in run.fig.axes[0].containers if type(c).__name__ == "ErrorbarContainer"][0]
        segs = cont.lines[2][0].get_segments()
        assert len(segs) == N and sum(1 for g in segs if len(g)) == N - 2


def test_bar_multi_series_yerr(tmp_path):
    b = build(
        tmp_path,
        series=[
            series(y=1, eb=EB(y=ES(column="__idx__2"))),
            series(y=5, eb=EB(y=ES(symmetric=False, column="__idx__6", columnMinus="__idx__3"))),
            series(y=1),
        ],
        plot_type="bar",
    )
    text = b.script.text
    assert '"y1_err": y1_err,' in text and '"y2_err_plus": y2_err_plus,' in text and '"y2_err_minus": y2_err_minus,' in text
    assert 'yerr=bar_data["y1_err"]' in text and 'yerr=[bar_data["y2_err_minus"], bar_data["y2_err_plus"]]' in text
    summary = b.check(lambda fig: None)
    assert summary[0]["errorbars"] == 2


def test_bar_multi_series_fixed(tmp_path):
    b = build(tmp_path, series=[series(y=1, eb=EB(y=ES("fixed", value=1))), series(y=5)], plot_type="bar")
    assert "yerr=1.0" in b.script.text
    assert b.check(lambda fig: None)[0]["errorbars"] == 1


def test_bar_secondary_axis(tmp_path):
    b = build(tmp_path, series=[series(y=1, secondaryAxis=True, eb=EB(y=ES("fixed", value=1)))], plot_type="bar")
    assert "ax2.bar(" in b.script.text and "yerr=1.0" in b.script.text
    assert [s["errorbars"] for s in b.check(lambda fig: None)] == [0, 1]


# ---------------------------------------------------------------- 一致・注入・手順


def test_full_script_and_auto_render_agree_for_every_kind(tmp_path):
    kinds = [
        ("line", [series(x=0, eb=EB(y=ES(column="__idx__2"), x=ES("fixed", value=0.1)))]),
        ("scatter", [series(x=0, eb=EB(y=ES("fixed", symmetric=False, value=1, valueMinus=2)))]),
        ("bar", [series(eb=EB(y=ES(column="__idx__2")))]),
    ]
    for plot_type, ser in kinds:
        b = build(tmp_path, series=ser, plot_type=plot_type)
        assert b.check(lambda fig: None)[0]["errorbars"] >= 1


def test_error_step_message_and_field(tmp_path):
    b = build(tmp_path, series=[series(eb=EB(y=ES(column="__idx__2")))])
    lines = b.script.text.split("\n")
    n = next(i for i, ln in enumerate(lines, start=1) if ln.startswith("y_err = pd.to_numeric"))
    step = b.script.step_for_line(n)
    assert step.field == "系列1のY誤差" and "エラーバーを描けませんでした" in step.message
    call = next(i for i, ln in enumerate(lines, start=1) if ln.startswith("draw_error_bars("))
    assert b.script.step_for_line(call).field == "系列1のY誤差"
    plot_line = next(i for i, ln in enumerate(lines, start=1) if ln.startswith("ax.plot(x[ok]"))
    assert plot_line > call and b.script.step_for_line(plot_line).field is None


def test_injection_in_column_names_and_colors(tmp_path):
    evil = 'e"\'\n__import__("os").system("echo pwned")  #\r\x0b'
    df = frame().rename(columns={"e": evil})
    b = build(tmp_path, df, series=[series(color="#112233", eb=EB(y=ES(column="__idx__2")))])
    text = b.script.text
    assert "pwned" not in "".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("#") and "#" not in ln)
    for ln in text.split("\n"):
        assert "\r" not in ln and "\x0b" not in ln
    assert comment_text(evil) in text
    with b.full() as run:
        assert bars_of(run.fig.axes[0])
    # 色・値は literal() の出力だけで書かれる
    assert f"color={literal('#112233')}" in text
    assert "capsize=3.0" in text


def test_helper_text_is_numpy_matplotlib_only_and_literal_values():
    src = "\n".join(ERROR_BAR_FUNCTION)
    assert "import" not in src and "pd." not in src
    compile(src, "helper", "exec")
    assert re.search(r"def draw_error_bars\(ax, x, y, low, high, \*, direction", src)


def test_fixed_value_literal_forms(tmp_path):
    b = build(tmp_path, series=[series(eb=EB(y=ES("fixed", value="0.5")))])
    assert "y[ok] - 0.5, y[ok] + 0.5" in b.script.text


def test_caps_are_markers_at_finite_ends_only():
    """両端の短い線は、有限な端点にだけ付く（NaN の区切りには付かない）。片側だけ有限でも付く。"""
    from matplotlib.figure import Figure

    ns = {}
    exec("import numpy as np\n" + "\n".join(ERROR_BAR_FUNCTION), ns)
    ax = Figure().subplots()
    x = np.array([0.0, 1.0, 2.0])
    ns["draw_error_bars"](ax, x, x, [0.0, np.nan, 1.0], [1.0, 2.0, np.nan], capsize=3)
    ns["draw_error_bars"](ax, x, x, [0.0, 1.0, 2.0], [1.0, 2.0, 3.0], direction="x", capsize=0)
    line_y, line_x = bars_of(ax)
    assert line_y.get_marker() == "_" and line_x.get_marker() == "None"
    ends = np.asarray(line_y.get_ydata(), dtype=float)
    drawn = np.flatnonzero(np.isfinite(ends))  # 記号は有限な頂点にだけ描かれる
    assert list(drawn) == [0, 1, 4, 6] and not np.isfinite(ends[2::3]).any()
