"""Phase 5c: グラフの種類 第1弾（G7: step / barh / barStacked / hist / scatterColor）。

生成コードを CPython（Agg）で実行して artist を検査し、「全体を実行した図」と「自動描画用の図」の要約の一致も確かめる。
"""
import numpy as np
import pandas as pd
import pytest

from mplgui.errors import UserError
from mplgui.settings import MAX_HIST_BINS, parse_settings
from style_helpers import Built, plan_of, raw_settings, series

pytestmark = pytest.mark.unit

CATS = ["A", "B", "C", "D", "E"]


def cf():
    """カテゴリ・正負と欠けた値・色の値（数値にできない値を含む）・数値の列。"""
    return pd.DataFrame(
        {
            "cat": CATS,  # 0
            "a": [3, -2, 5, np.nan, 1.0],  # 1
            "b": [1, 2, -3, 4, 5.0],  # 2
            "z": ["1", "2", "bad", "4", "5"],  # 3: 色の値（3行目は数値にできない）
            "t": [0.0, 1, 2, 3, 4],  # 4
        }
    )


def settings_of(plot_type, **kw):
    return parse_settings(raw_settings(plot_type=plot_type, **kw))


def mutate_plot(**plot):
    def fn(raw):
        raw["plot"].update(plot)

    return fn


def build(tmp_path, plot_type, series_list, df=None, **plot):
    def mutate(raw):
        raw["plot"]["xColumn"] = plot.pop("xColumn", "__idx__0") if plot_type.startswith("bar") else ""
        raw["plot"].update(plot)

    return Built(tmp_path, df=df if df is not None else cf(), series_list=series_list, plot_type=plot_type, mutate=mutate)


def colored(**kw):
    return series(y=1, x=4, colorColumn="__idx__3", **kw)


def rects(ax, n=None):
    """BarContainer の棒をすべて返す（容器の並び順）。"""
    out = []
    for c in ax.containers:
        if type(c).__name__ == "BarContainer":
            out.append(list(c.patches))
    return out


# ---------------------------------------------------------------- 設定（settings）


def test_new_plot_types_accepted_and_defaults():
    for t in ("step", "barh", "barStacked", "hist"):
        s = settings_of(t)
        assert s.plot.type == t
    d = parse_settings(raw_settings(plot_type="line"))
    assert (d.plot.step_where, d.plot.hist_bins, d.plot.hist_density, d.plot.colormap, d.plot.colorbar_label) == ("post", None, False, "viridis", "")
    assert d.series[0].color_column == ""


def test_step_hist_colormap_validated_only_for_own_type():
    bad = {"step": {"where": "zzz"}, "hist": {"bins": 0, "density": "x"}, "colormap": "nope", "colorbarLabel": 5}
    for t in ("line", "scatter", "bar", "barh"):
        parse_settings(raw_settings(plot_type=t, mutate=mutate_plot(**bad)))  # 隠れているので、エラーにならない
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(plot_type="step", mutate=mutate_plot(step={"where": "zzz"})))
    assert e.value.field == "段の付き方"
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(plot_type="hist", mutate=mutate_plot(hist={"bins": 0, "density": False})))
    assert e.value.field == "区間の数"
    with pytest.raises(UserError):
        parse_settings(raw_settings(plot_type="hist", mutate=mutate_plot(hist={"bins": MAX_HIST_BINS + 1, "density": False})))
    with pytest.raises(UserError):
        parse_settings(raw_settings(plot_type="hist", mutate=mutate_plot(hist={"bins": 3, "density": "yes"})))
    assert parse_settings(raw_settings(plot_type="hist", mutate=mutate_plot(hist={"bins": "12", "density": True}))).plot.hist_bins == 12
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([colored()], plot_type="scatterColor", mutate=mutate_plot(colormap="nope")))
    assert e.value.field == "カラーマップ"


def test_color_column_required_only_for_scatter_color():
    parse_settings(raw_settings([series(colorColumn=123)], plot_type="scatter"))  # 隠れている
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(), series()], plot_type="scatterColor"))
    assert str(e.value) == "系列1の色分けの列を選んでください。" and e.value.field == "系列1の色分けの列"
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([colored(), series(colorColumn="")], plot_type="scatterColor"))
    assert e.value.field == "系列2の色分けの列"
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(colorColumn="abc")], plot_type="scatterColor"))
    assert e.value.field == "系列1の色分けの列"


def test_hidden_marker_fill_fits_error_bars_and_y2():
    bad_marker = {"marker": "zzz", "fill": {"lower": "x", "upper": ""}, "secondaryAxis": "yes", "errorBars": {"x": {"mode": "zzz"}, "y": {"mode": "zzz"}}}
    fit = [{"series": "s1", "model": "zzz"}]
    # バー系: 点の形・帯・X方向のエラーバー・近似曲線は隠れている
    for t in ("bar", "barh", "barStacked", "hist"):
        s = parse_settings(raw_settings([series(**{k: v for k, v in bad_marker.items() if k not in {"secondaryAxis", "errorBars"}})], plot_type=t, fits=fit))
        assert s.fits == () and s.series[0].marker == "auto" and not s.series[0].fill.enabled
    # 第2Y軸は barh / barStacked / hist / scatterColor で隠れる
    for t in ("barh", "barStacked", "hist"):
        s = parse_settings(raw_settings([series(secondaryAxis="yes")], plot_type=t))
        assert s.series[0].secondary_axis is False
    s = parse_settings(raw_settings([colored(secondaryAxis=True)], plot_type="scatterColor"))
    assert s.series[0].secondary_axis is False
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(secondaryAxis="yes")], plot_type="bar"))
    # エラーバー: X は barh / barStacked / hist で隠れ、Y は barStacked / hist で隠れる。barh の Y は使う
    bad_x = {"x": {"mode": "zzz"}}
    parse_settings(raw_settings([series(errorBars=bad_x)], plot_type="barh"))
    bad_y = {"y": {"mode": "zzz"}}
    parse_settings(raw_settings([series(errorBars=bad_y)], plot_type="barStacked"))
    parse_settings(raw_settings([series(errorBars=bad_y)], plot_type="hist"))
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(errorBars=bad_y)], plot_type="barh"))
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(errorBars=bad_x)], plot_type="step"))
    # 点の形「なし」は scatterColor でもエラー、step では使える
    with pytest.raises(UserError):
        parse_settings(raw_settings([colored(marker="none")], plot_type="scatterColor"))
    parse_settings(raw_settings([series(marker="none")], plot_type="step"))


def test_effective_marker_size_step_and_scatter_color():
    s = parse_settings(raw_settings([series()], plot_type="step")).series[0]
    assert s.effective_marker_size("step") == 0.0 and s.effective_marker_size("scatterColor") == 24.0
    s2 = parse_settings(raw_settings([colored(markerSize=0)], plot_type="scatterColor")).series[0]
    assert s2.effective_marker_size("scatterColor") == 24.0


# ---------------------------------------------------------------- step


def test_step_drawstyle_and_where(tmp_path):
    for where in ("pre", "mid", "post"):
        bt = build(tmp_path, "step", [series(y=1, x=4)], step={"where": where})
        assert f'drawstyle="steps-{where}"' in bt.script.text
        s = bt.check(lambda f: None)
        assert s[0]["drawstyles"] == [f"steps-{where}"]


def test_step_default_post_and_line_unchanged(tmp_path):
    assert "drawstyle" not in build(tmp_path, "line", [series(y=1, x=4)]).script.text
    s = build(tmp_path, "step", [series(y=1, x=4)]).check(lambda f: None)
    assert s[0]["drawstyles"] == ["steps-post"] and s[0]["markers"] == ["None"]


def test_step_band_markers_errorbars_and_y2(tmp_path):
    df = cf()
    df["lo"] = df["b"] - 1
    df["hi"] = df["b"] + 1
    sl = [
        series(y=2, x=4, fill={"lower": "__idx__5", "upper": "__idx__6", "alpha": 0.3}, marker="s", errorBars={"y": {"mode": "fixed", "value": 0.5}}),
        series(y=1, x=4, secondaryAxis=True),
    ]
    bt = build(tmp_path, "step", sl, df=df, step={"where": "mid"})
    assert 'step="mid"' in bt.script.text
    s = bt.check(lambda f: None)
    assert s[0]["bands"] == 1 and s[0]["markers"] == ["s"] and s[0]["errorbars"] == 1
    assert len(s) == 2 and s[1]["markers"] == ["None"]
    assert set(s[0]["drawstyles"]) == {"steps-mid"}


def test_step_fit_works(tmp_path):
    bt = Built(tmp_path, df=cf(), series_list=[series(y=2, x=4)], plot_type="step", fits=[{"series": "s1"}])
    s = bt.check(lambda f: None)
    assert s[0]["fitlines"] == 1


# ---------------------------------------------------------------- barh


def test_barh_single_series(tmp_path):
    bt = build(tmp_path, "barh", [series(y=1)])
    assert "ax.barh(" in bt.script.text and "ax.bar(" not in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        (bars,) = rects(ax)
        assert [round(b.get_width(), 6) for b in bars] == [3.0, -2.0, 5.0, 1.0]  # 欠けた行は描かない
        assert [t.get_text() for t in ax.get_yticklabels()] == ["A", "B", "C", "E"]
        assert ax.get_xlabel() == "a [1]" and ax.get_ylabel() == "cat"

    s = bt.check(fn)
    assert s[0]["bars"]["horizontal"] == 4 and s[0]["bars"]["vertical"] == 0


def test_barh_multi_series_offsets_vertical(tmp_path):
    bt = build(tmp_path, "barh", [series(y=1), series(y=2)])
    assert "height = 0.8 / 2" in bt.script.text and "tick_step" in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        first, second = rects(ax)
        assert len(first) == len(second) == 5
        assert all(abs(b.get_height() - 0.4) < 1e-9 for b in first)
        assert first[0].get_y() < second[0].get_y()  # 系列1は下、系列2は上
        assert [t.get_text() for t in ax.get_yticklabels()] == CATS
        assert ax.get_xlabel() == "a [1]" and ax.get_ylabel() == "cat"

    bt.check(fn)


def test_barh_error_bars_use_xerr(tmp_path):
    df = cf()
    df["e"] = [0.5, 0.25, 1, 1, 0.1]
    bt = build(tmp_path, "barh", [series(y=2, errorBars={"y": {"mode": "column", "column": "__idx__5"}})], df=df)
    assert "xerr=" in bt.script.text and "yerr=" not in bt.script.text
    s = bt.check(lambda f: None)
    assert s[0]["errorbars"] >= 1
    bt = build(tmp_path, "barh", [series(y=1), series(y=2, errorBars={"y": {"mode": "fixed", "value": 1}})])
    assert "xerr=1" in bt.script.text
    bt.check(lambda f: None)


def test_barh_axis_settings_are_physical(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        raw["axes"]["x"]["label"] = "値"
        raw["axes"]["y"]["label"] = "品目"
        raw["axes"]["y"]["scale"] = "log"  # 縦軸（カテゴリ）のスケールは使わない
        raw["axes"]["x"]["min"] = -5
        raw["axes"]["x"]["max"] = 10

    bt = Built(tmp_path, df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barh", mutate=mutate)
    assert "set_yscale" not in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        assert ax.get_xlabel() == "値" and ax.get_ylabel() == "品目"
        assert ax.get_xlim() == (-5, 10) and ax.get_yscale() == "linear"

    bt.check(fn)


def test_barh_major_step_on_category_axis(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        raw["axes"]["y"]["majorStep"] = 2

    # 1系列（文字列のカテゴリ）: Y 軸に MultipleLocator
    bt = Built(tmp_path, df=cf(), series_list=[series(y=2)], plot_type="barh", mutate=mutate)
    s = bt.check(lambda f: None)
    assert s[0]["ymajor"] == "MultipleLocator" and "ticker.MultipleLocator(2)" in bt.script.text
    # 複数系列: tick_step で間引く
    bt = Built(tmp_path, df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barh", mutate=mutate)
    assert "tick_step = 2" in bt.script.text and "set_yticks(positions[::tick_step])" in bt.script.text
    s = bt.check(lambda f: None)
    assert s[0]["yticklabels"] == ["A", "C", "E"]
    # 主目盛が多すぎるときのエラーは Y 軸
    def many(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        raw["axes"]["y"]["majorStep"] = 1

    big = pd.DataFrame({"cat": [f"c{i}" for i in range(400)], "v": range(400)})
    with pytest.raises(UserError) as e:
        plan_of(df=big, series_list=[series(y=1), series(y=1)], plot_type="barh", mutate=many)
    assert e.value.field == "Y軸の主目盛の間隔"


def test_barh_numeric_x_single_series_is_numeric_axis(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__4"

    bt = Built(tmp_path, df=cf(), series_list=[series(y=2)], plot_type="barh", mutate=mutate)
    s = bt.check(lambda f: None)
    assert s[0]["ylabel"] == "t" and s[0]["bars"]["horizontal"] == 5
    assert bt.plan.axes.y.kind == "number"


def test_barh_annotations_y_is_category_index(tmp_path):
    ann = [
        {"kind": "hline", "y": "1.5"},
        {"kind": "vline", "x": "2"},
        {"kind": "text", "x": "2", "y": "3", "text": "メモ"},
    ]
    bt = Built(
        tmp_path, df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barh", annotations=ann,
        mutate=lambda raw: raw["plot"].update(xColumn="__idx__0"),
    )
    assert [a.kind for a in bt.plan.annotations] == ["hline", "vline", "text"]
    s = bt.check(lambda f: None)
    assert s[0]["annotations"] == {"texts": 1, "hlines": 1, "vlines": 1, "hspans": 0, "vspans": 0}
    with pytest.raises(UserError) as e:
        plan_of(df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barh", annotations=[{"kind": "hline", "y": "abc"}], mutate=lambda raw: raw["plot"].update(xColumn="__idx__0"))
    assert e.value.field == "注釈1のY" and "カテゴリ" in str(e.value)


def test_barh_source_must_be_shared_and_x_axis_log_is_value_axis(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        raw["axes"]["x"]["scale"] = "log"

    bt = Built(tmp_path, df=cf().assign(a=lambda d: d["a"].abs() + 1), series_list=[series(y=1)], plot_type="barh", mutate=mutate)
    assert bt.check(lambda f: None)[0]["xscale"] == "log"


# ---------------------------------------------------------------- barStacked


def test_stacked_positive_negative_and_missing_as_zero(tmp_path):
    bt = build(tmp_path, "barStacked", [series(y=1), series(y=2)])
    assert "stack_pos" in bt.script.text and "stack_neg" in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        first, second = rects(ax)
        assert [b.get_y() for b in first] == [0, 0, 0, 0, 0]
        assert [b.get_height() for b in first] == [3, -2, 5, 0, 1]  # 欠けた値は 0
        # 正と負は別に積む: 行0 は 3 の上、行1 は系列1が負なので系列2（正）は 0 から、行2 は系列2が負なので 0 から下へ
        assert [b.get_y() for b in second] == [3, 0, 0, 0, 1]
        assert [b.get_height() for b in second] == [1, 2, -3, 4, 5]
        assert [b.get_x() + b.get_width() / 2 for b in first] == [0, 1, 2, 3, 4]
        assert [t.get_text() for t in ax.get_xticklabels()] == CATS

    s = bt.check(fn)
    assert s[0]["bars"]["stacked"] == 1 and s[0]["bars"]["vertical"] == 10


def test_stacked_negative_stack_depth(tmp_path):
    df = pd.DataFrame({"cat": ["A", "B"], "p": [2.0, -1.0], "q": [-3.0, -2.0], "r": [4.0, 1.0]})
    bt = build(tmp_path, "barStacked", [series(y=1), series(y=2), series(y=3)], df=df)

    def fn(fig):
        p, q, r = rects(fig.axes[0])
        assert [b.get_y() for b in q] == [0, -1]  # 負の値は、負の段の下へ
        assert [(b.get_y(), b.get_height()) for b in r] == [(2, 4), (0, 1)]
        assert fig.axes[0].get_ylim()[0] <= -3 and fig.axes[0].get_ylim()[1] >= 6  # 積んだ合計が入る

    bt.check(fn)
    ext = bt.plan.axes.y
    assert ext.kind == "number"


def test_stacked_single_series_uses_positions_and_drops_all_missing_rows(tmp_path):
    df = cf()
    df.loc[3, ["a", "b"]] = np.nan
    bt = build(tmp_path, "barStacked", [series(y=1)], df=df)
    assert "positions" in bt.script.text and "bottom=" in bt.script.text

    def fn(fig):
        (bars,) = rects(fig.axes[0])
        assert [round(b.get_height(), 6) for b in bars] == [3, -2, 5, 1]  # Y が欠けた行は描かない

    bt.check(fn)
    both = build(tmp_path, "barStacked", [series(y=1), series(y=2)], df=df)

    def fn2(fig):
        assert [t.get_text() for t in fig.axes[0].get_xticklabels()] == ["A", "B", "C", "E"]  # 全系列が欠けた行は描かない

    both.check(fn2)


def test_stacked_hides_error_bars_and_y2_and_requires_one_source(tmp_path):
    s = parse_settings(raw_settings([series(errorBars={"y": {"mode": "fixed", "value": 1}}, secondaryAxis=True)], plot_type="barStacked"))
    assert s.series[0].error_bars.y.mode == "none" and not s.series[0].secondary_axis
    bt = build(tmp_path, "barStacked", [series(y=1, errorBars={"y": {"mode": "fixed", "value": 1}})])
    assert "yerr" not in bt.script.text
    assert bt.plan.series[0].y_err is None


def test_stacked_tick_step(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        raw["axes"]["x"]["majorStep"] = 2

    bt = Built(tmp_path, df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barStacked", mutate=mutate)
    assert "tick_step = 2" in bt.script.text
    assert bt.check(lambda f: None)[0]["xticklabels"] == ["A", "C", "E"]


# ---------------------------------------------------------------- hist


def hist_frame(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"a": rng.normal(0, 1, n), "b": rng.normal(3, 2, n), "c": ["x"] * n})


def test_hist_shared_bins_and_side_by_side(tmp_path):
    df = hist_frame()
    bt = Built(tmp_path, df=df, series_list=[series(y=0), series(y=1)], plot_type="hist", mutate=mutate_plot(hist={"bins": 8, "density": False}))
    assert "np.histogram_bin_edges(np.concatenate([hist_1, hist_2]), bins=8)" in bt.script.text
    assert 'hist_1 = pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()' in bt.script.text
    edges = np.histogram_bin_edges(np.concatenate([df["a"], df["b"]]), bins=8)

    def fn(fig):
        ax = fig.axes[0]
        first, second = rects(ax)
        assert len(first) == len(second) == 8
        counts = [sum(b.get_height() for b in c) for c in (first, second)]
        assert counts == [200, 200]
        width = edges[1] - edges[0]
        assert all(abs(b.get_width() - 0.8 * width / 2) < 1e-9 for b in first)  # 区間ごとに系列を横に並べる（幅は区間の 0.8 を系列数で割る）
        assert second[0].get_x() > first[0].get_x()
        assert ax.get_xlabel() == "a [0]" and ax.get_ylabel() == "度数"

    s = bt.check(fn)
    assert s[0]["bars"]["containers"] == [8, 8] and bt.plan.hist.bin_count == 8


def test_hist_auto_bins_single_series_and_density(tmp_path):
    df = hist_frame()
    bt = Built(tmp_path, df=df, series_list=[series(y=0)], plot_type="hist", mutate=mutate_plot(hist={"bins": None, "density": True}))
    assert 'bins="auto"' in bt.script.text and "plt.setp" not in bt.script.text
    assert "np.concatenate" not in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        (bars,) = rects(ax)
        area = sum(b.get_height() * b.get_width() for b in bars)
        assert abs(area - 1) < 1e-9
        assert ax.get_ylabel() == "確率密度"

    s = bt.check(fn)
    assert s[0]["bars"]["containers"] == [len(np.histogram_bin_edges(df["a"], "auto")) - 1]


def test_hist_ignores_x_column_and_allows_different_sources(tmp_path):
    df = hist_frame()
    bt = Built(tmp_path, df=df, series_list=[series(y=0, x="__idx__99")], plot_type="hist")  # X は隠れている（範囲外でもエラーにならない）
    bt.check(lambda f: None)
    # 長さの違う別のデータ元（行の対応は要らない）
    from mplgui.dataprep import plan_plot
    from mplgui.loader import load_file

    a = load_file(df[["a"]].to_csv(index=False).encode(), "a.csv", "", True).df
    b = load_file(df[["b"]].head(50).to_csv(index=False).encode(), "b.csv", "", True).df
    raw = raw_settings([series(y=0), series(y=0, source="d2")], plot_type="hist")
    raw["load"]["files"] = [{"id": "d1", "name": "a.csv", "sheet": ""}, {"id": "d2", "name": "b.csv", "sheet": ""}]
    plan = plan_plot({"d1": a, "d2": b}, parse_settings(raw))
    assert [s.data_var for s in plan.series] == ["df1", "df2"]


def test_hist_per_series_alpha_and_style(tmp_path):
    bt = Built(
        tmp_path, df=hist_frame(), series_list=[series(y=0, alpha=0.5, lineWidth=3), series(y=1)], plot_type="hist",
        mutate=mutate_plot(hist={"bins": 5, "density": False}),
    )
    assert bt.script.text.count("plt.setp(") == 2 and "alpha=0.5" in bt.script.text

    def fn(fig):
        first, second = rects(fig.axes[0])
        assert first[0].get_alpha() == 0.5 and second[0].get_alpha() is None
        assert first[0].get_linewidth() == 3

    bt.check(fn)


def test_hist_auto_bins_over_limit_is_error():
    from mplgui.dataprep import plan_plot

    df = pd.DataFrame({"v": np.random.default_rng(1).lognormal(0, 3, 400000)})  # 裾が重く、自動の区間が 1000 を超える
    with pytest.raises(UserError) as e:
        plan_plot(df, parse_settings(raw_settings([series(y=0)], plot_type="hist")))
    assert e.value.field == "区間の数" and "1000 個まで" in str(e.value) and "1265 個" in str(e.value) and "指定してください" in str(e.value)
    plan = plan_plot(df, parse_settings(raw_settings([series(y=0)], plot_type="hist", mutate=mutate_plot(hist={"bins": 50, "density": False}))))
    assert plan.hist.bin_count == 50


def test_hist_no_values_and_non_numeric_warning(tmp_path):
    with pytest.raises(UserError) as e:
        plan_of(df=hist_frame(), series_list=[series(y=2)], plot_type="hist")
    assert "数値" in str(e.value)
    df = hist_frame()
    df["d"] = ["1", "2", "oops"] + ["3"] * 197
    plan = plan_of(df=df, series_list=[series(y=3), series(y=2)], plot_type="hist")
    assert any("oops" in w["message"] and w["series"] == 1 for w in plan.warnings)
    assert plan.series[1].has_points is False and plan.plotted_count == 1


def test_hist_series_without_values_is_skipped_in_code(tmp_path):
    df = hist_frame()
    df["e"] = [None] * len(df)
    bt = Built(tmp_path, df=df, series_list=[series(y=0), series(y=3)], plot_type="hist", mutate=mutate_plot(hist={"bins": 4, "density": False}))
    assert "この系列は描かない" in bt.script.text and "plt.setp" not in bt.script.text
    bt.check(lambda f: None)


def test_hist_extents_feed_tick_estimate():
    # Y の主目盛の本数の見積もりに、0 から最大の度数が使われる
    with pytest.raises(UserError) as e:
        plan_of(df=hist_frame(), series_list=[series(y=0)], plot_type="hist", mutate=lambda raw: raw["axes"]["y"].update(majorStep=0.01))
    assert e.value.field == "Y軸の主目盛の間隔"
    plan = plan_of(df=hist_frame(), series_list=[series(y=0)], plot_type="hist", mutate=lambda raw: raw["axes"]["y"].update(majorStep=5))
    assert plan.hist.max_height > 0 and plan.axes.y.major_step == 5


# ---------------------------------------------------------------- scatterColor


def test_scatter_color_range_shared_across_series_and_colorbar(tmp_path):
    df = cf()
    df["z2"] = [10.0, 20, 30, 40, 50]
    sl = [colored(), series(y=2, x=4, colorColumn="__idx__5")]
    bt = Built(tmp_path, df=df, series_list=sl, plot_type="scatterColor", mutate=mutate_plot(colormap="plasma", colorbarLabel="温度 (℃)"))
    assert "color_norm" in bt.script.text and "plt.Normalize()" in bt.script.text
    # データ由来の数値をリテラルにしない
    for token in ("50", "10.0"):
        assert f"vmax={token}" not in bt.script.text and f"vmin={token}" not in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        scatters = [c for c in ax.collections if c.get_label() == "_color"]
        assert len(scatters) == 2
        assert all(c.get_cmap().name == "plasma" for c in scatters)
        # 描いた点（X・Y・色がそろった点）の色の最小〜最大: 系列1は 3 行目(bad)と4行目(Y が欠け)を除く → {1,2,5}、系列2は 10..50
        assert scatters[0].get_clim() == (1.0, 50.0) and scatters[1].get_clim() == (1.0, 50.0)
        assert sorted(scatters[0].get_array().tolist()) == [1.0, 2.0, 5.0]

    s = bt.check(fn)
    assert s[0]["colorbar"] == {"label": "温度 (℃)", "cmap": "plasma", "vmin": 1.0, "vmax": 50.0}
    assert len(s) == 1  # カラーバーの Axes は一覧に入れない
    assert bt.plan.colorbar.label == "温度 (℃)"


def test_scatter_color_default_label_is_first_series_color_column(tmp_path):
    bt = Built(tmp_path, df=cf(), series_list=[colored()], plot_type="scatterColor")
    s = bt.check(lambda f: None)
    assert s[0]["colorbar"]["label"] == "z [3]" and s[0]["colorbar"]["cmap"] == "viridis"


def test_scatter_color_range_excludes_undrawn_points(tmp_path):
    df = cf()
    df["z"] = [1, 2, 3, 100, 5]
    df.loc[3, "a"] = np.nan  # 値 100 の行は Y が欠けているので描かない
    bt = Built(tmp_path, df=df, series_list=[colored()], plot_type="scatterColor")
    s = bt.check(lambda f: None)
    assert (s[0]["colorbar"]["vmin"], s[0]["colorbar"]["vmax"]) == (1.0, 5.0)


def test_scatter_color_legend_markers_are_gray_and_legend_rule_unchanged(tmp_path):
    bt = Built(tmp_path, df=cf(), series_list=[colored(label="温度"), colored(label="")], plot_type="scatterColor", mutate=mutate_plot(legend={"location": "best"}))

    def fn(fig):
        legend = fig.axes[0].get_legend()
        assert [t.get_text() for t in legend.get_texts()] == ["温度", "a [1]"]
        for handle in legend.legend_handles:
            assert tuple(handle.get_facecolor()[0][:3]) == pytest.approx((0.5019607843137255, 0.5019607843137255, 0.5019607843137255))

    bt.check(fn)
    # 凡例の位置が「なし」なら出さない（scatter と同じ）
    none = Built(tmp_path, df=cf(), series_list=[colored(label="温度")], plot_type="scatterColor", mutate=mutate_plot(legend={"location": "none"}))
    none.check(lambda f: None)
    with none.full() as run:
        assert run.fig.axes[0].get_legend() is None


def test_scatter_color_marker_shape_and_alpha_in_legend(tmp_path):
    bt = Built(tmp_path, df=cf(), series_list=[colored(marker="^", alpha=0.5)], plot_type="scatterColor")
    assert 'marker="^"' in bt.script.text
    s = bt.check(lambda f: None)
    assert s[0]["alphas"] == [0.5]


def test_scatter_color_warns_once_per_series_with_examples_and_hints(tmp_path):
    df = cf()
    df["z"] = ["1", "2", "bad", "1,5", "5"]
    df.loc[1, "z"] = None  # 空欄は警告しない
    plan = plan_of(df=df, series_list=[series(y=2, x=4, colorColumn="__idx__3"), series(y=2, x=4, colorColumn="__idx__3")], plot_type="scatterColor")
    msgs = [w for w in plan.warnings if "色分け" in w["message"]]
    assert [w["series"] for w in msgs] == [1, 2]
    assert 'z' in msgs[0]["message"] and '"bad"' in msgs[0]["message"] and "その点は描きません" in msgs[0]["message"]
    assert "小数点" in msgs[0]["message"]
    assert "2件" in msgs[0]["message"]  # bad と 1,5 だけ（空欄は数えない）


def test_scatter_color_errors(tmp_path):
    df = cf()
    df["d"] = pd.date_range("2026-01-01", periods=5).strftime("%Y-%m-%d")
    with pytest.raises(UserError) as e:
        plan_of(df=df, series_list=[series(y=1, x=4, colorColumn="__idx__5")], plot_type="scatterColor")
    assert e.value.field == "系列1の色分けの列" and "日時" in str(e.value)
    with pytest.raises(UserError) as e:
        plan_of(df=df, series_list=[series(y=1, x=4, colorColumn="__idx__99")], plot_type="scatterColor")
    assert e.value.field == "系列1の色分けの列"
    all_bad = cf()
    all_bad["z"] = ["x"] * 5
    with pytest.raises(UserError):
        plan_of(df=all_bad, series_list=[colored()], plot_type="scatterColor")


def test_scatter_color_bands_errorbars_fits_use_drawn_points(tmp_path):
    df = cf()
    df["lo"] = df["b"] - 1
    df["hi"] = df["b"] + 1
    df["t"] = [0.0, 1, 2, 3, 5]
    sl = [series(y=2, x=4, colorColumn="__idx__3", fill={"lower": "__idx__5", "upper": "__idx__6", "alpha": 0.2}, errorBars={"y": {"mode": "fixed", "value": 0.3}})]
    bt = Built(tmp_path, df=df, series_list=sl, plot_type="scatterColor", fits=[{"series": "s1"}])
    s = bt.check(lambda f: None)
    assert s[0]["bands"] == 1 and s[0]["errorbars"] == 1 and s[0]["fitlines"] == 1


def test_scatter_color_datetime_x(tmp_path):
    df = cf()
    df["d"] = pd.date_range("2026-01-01", periods=5).strftime("%Y-%m-%d")
    bt = Built(tmp_path, df=df, series_list=[series(y=1, x=5, colorColumn="__idx__4")], plot_type="scatterColor")
    assert "mdates" in bt.script.text
    bt.check(lambda f: None)


# ---------------------------------------------------------------- 全体と自動描画の一致・ステップ・注入


@pytest.mark.parametrize("plot_type", ["step", "barh", "barStacked", "hist", "scatterColor", "bar", "scatter", "line"])
def test_full_and_auto_summaries_match(tmp_path, plot_type):
    sl = [colored(), series(y=2, x=4, colorColumn="__idx__3")] if plot_type == "scatterColor" else [series(y=1, x=4), series(y=2, x=4)]
    if plot_type == "hist":
        sl = [series(y=1), series(y=2)]
    bt = build(tmp_path, plot_type, sl)
    bt.check(lambda f: None)


def test_steps_registered_with_japanese_messages(tmp_path):
    bt = build(tmp_path, "scatterColor", [colored()])
    messages = [s.message for s in bt.script.steps]
    assert any("カラーバー" in m for m in messages)
    fields = [s.field for s in bt.script.steps]
    assert "系列1の色分けの列" in fields and "カラーマップ" in fields
    assert build(tmp_path, "hist", [series(y=1)]).script.steps


def test_injection_in_column_names_labels(tmp_path):
    import ast

    evil = '"); import os; os.system("echo hi") #'
    df = pd.DataFrame({'c"\'\n' + evil: ["a", "b", "c"], "v" + evil: [1.0, 2, 3], "z" + evil: [1.0, 2, 3], "t": [0.0, 1, 2]})
    label = "'''\n" + evil
    for plot_type in ("barh", "barStacked", "hist", "scatterColor", "step"):
        sl = [series(y=1, x=3, label=label, colorColumn="__idx__2")]
        bt = build(tmp_path, plot_type, sl, df=df, colorbarLabel=label)
        calls = [n for n in ast.walk(ast.parse(bt.script.text)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "system"]
        assert not calls  # 注入された文字列は、文字列のリテラルの中にだけ現れる
        with bt.full() as run:
            assert run.fig is not None
            assert "echo hi" not in run.output


def test_colormap_injection_is_rejected_by_validation():
    with pytest.raises(UserError):
        parse_settings(raw_settings([colored()], plot_type="scatterColor", mutate=mutate_plot(colormap='viridis"); import os #')))


# ---------------------------------------------------------------- 追加の確認（隠れた設定・scatterColor の端の場合）


def test_barh_hides_y_scale(tmp_path):
    def mutate(raw):
        raw["plot"]["xColumn"] = "__idx__0"
        y = raw["axes"]["y"]
        y.update(scale="log", min=-1, max=10, minorTicks="on", minorDivisions=3, majorStep=2)

    bt = Built(tmp_path, df=cf(), series_list=[series(y=1), series(y=2)], plot_type="barh", mutate=mutate)
    assert "set_yscale" not in bt.script.text and "set_ylim(bottom=-1.0, top=10.0)" in bt.script.text
    s = bt.check(lambda f: None)
    assert s[0]["yscale"] == "linear"
    # 不正なスケールの値も検証しない。バー（縦）では今までどおり検証する
    raw = raw_settings([series(y=1)], plot_type="barh", mutate=lambda r: r["axes"]["y"].update(scale="zzz"))
    assert parse_settings(raw).axes.y.scale == "linear"
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(y=1)], plot_type="bar", mutate=lambda r: r["axes"]["y"].update(scale="zzz")))
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(y=1)], plot_type="bar", mutate=lambda r: r["axes"]["y"].update(scale="log", min=-1)))


def test_stacked_and_hist_do_not_validate_error_bars_at_all():
    bad = {"capSize": 999, "y": {"mode": "zzz"}, "x": {"mode": "zzz"}}
    for t in ("barStacked", "hist"):
        s = parse_settings(raw_settings([series(errorBars=bad)], plot_type=t)).series[0]
        assert s.error_bars.y.mode == "none" and s.error_bars.x.mode == "none" and s.error_bars.cap_size == 3.0
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(errorBars={"capSize": 999})], plot_type="barh"))


def test_hist_does_not_resolve_or_validate_x_columns(tmp_path):
    bt = Built(
        tmp_path, df=hist_frame(), series_list=[series(y=0, x="__idx__99")], plot_type="hist",
        mutate=lambda raw: raw["plot"].update(xColumn="__idx__99"),
    )
    bt.check(lambda f: None)
    assert parse_settings(raw_settings([series(y=0)], plot_type="hist", mutate=lambda raw: raw["plot"].update(xColumn=5))).plot.x_column == ""
    # line / step などでは今までどおり X列を解決する
    with pytest.raises(UserError):
        plan_of(df=hist_frame(), series_list=[series(y=0, x="__idx__99")], plot_type="step")


def test_scatter_color_all_equal_colors_no_warning(tmp_path):
    import warnings

    df = cf()
    df["z"] = [7.0] * 5
    bt = Built(tmp_path, df=df, series_list=[colored()], plot_type="scatterColor")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings("ignore", message=".*missing from.*")
        warnings.filterwarnings("ignore", message=".*non-interactive.*")
        s = bt.check(lambda f: None)
        with bt.full() as run:
            run.fig.canvas.draw()
    assert s[0]["colorbar"]["vmin"] <= 7.0 <= s[0]["colorbar"]["vmax"]  # 範囲が1点のときは matplotlib が少し広げる


def test_scatter_color_series_without_points_is_skipped_everywhere(tmp_path):
    df = cf()
    df["w"] = ["x"] * 5  # 全部数値にできない色の値
    sl = [colored(label="描く"), series(y=2, x=4, colorColumn="__idx__5", label="描かない")]
    bt = Built(tmp_path, df=df, series_list=sl, plot_type="scatterColor")
    assert "この系列は描かない" in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        assert len([c for c in ax.collections if c.get_label() == "_color"]) == 1
        assert [t.get_text() for t in ax.get_legend().get_texts()] == ["描く"]

    s = bt.check(fn)
    assert s[0]["colorbar"]["vmin"] == 1.0
    assert bt.script.text.count("ax.scatter([]") == 1


def test_scatter_color_points_have_no_edge_and_compensated_size(tmp_path):
    # 点ごとに色が違うと縁を1点ずつ描くため遅い。縁は描かず、縁の太さ（1.5 pt）の分だけ点を大きくする（見た目の大きさは同じ）
    sl = [colored(), series(y=2, x=4, colorColumn="__idx__3", marker="x")]
    bt = Built(tmp_path, df=cf(), series_list=sl, plot_type="scatterColor")
    assert bt.script.text.count("点の縁は描かない") == 1

    def fn(fig):
        ax = fig.axes[0]
        filled, crosses = [c for c in ax.collections if c.get_label() == "_color"]
        assert list(filled.get_linewidths()) == [0.0]
        assert filled.get_sizes()[0] == pytest.approx((24 ** 0.5 + 1.5) ** 2)
        # x / + は線だけの点なので、縁を描き、大きさもそのまま
        assert crosses.get_linewidths()[0] > 0 and crosses.get_sizes()[0] == pytest.approx(24.0)
        # 凡例の見本も同じ大きさ・縁
        proxies = [c for c in ax.collections if c.get_label() not in ("_color",) and len(c.get_offsets()) == 0]
        assert proxies[0].get_sizes()[0] == pytest.approx((24 ** 0.5 + 1.5) ** 2) and list(proxies[0].get_linewidths()) == [0.0]

    bt.check(fn)


# ================================================================ Phase 5d: 箱ひげ図・バイオリン図・ヒートマップ（G8）

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

from mplgui import settings as settings_module  # noqa: E402
from mplgui.settings import MAX_HEATMAP_SIZE  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
NEW_TYPES = ("box", "violin", "heatmap")


def dist_frame(n=40, seed=1):
    """値の列 3 つ（a: 外れ値あり、b: 文字列を含む、c: 欠けた値だけ）と 1 行だけの列。"""
    rng = np.random.default_rng(seed)
    a = list(rng.normal(0, 1, n))
    a[0] = 15.0  # 外れ値
    b = [str(v) for v in rng.normal(3, 1, n)]
    b[1] = "bad"
    return pd.DataFrame({"a": a, "b": b, "c": [np.nan] * n, "one": [2.0] + [np.nan] * (n - 1)})


def grid_frame():
    """縦長の表: x（数値）・y（数値）・z（値）・tx（文字列）・ty（文字列）。3×2 の格子で (1, 0) の組が 1 つ欠け、(0, 0) は 2 回現れる。"""
    rows = [(0, 0, 1.0), (0, 0, 3.0), (0, 1, 4.0), (1, 1, 5.0), (2, 0, 6.0), (2, 1, 7.0)]
    df = pd.DataFrame(rows, columns=["x", "y", "z"])
    df["tx"] = df["x"].map({0: "low", 1: "mid", 2: "high"})
    df["ty"] = df["y"].map({0: "off", 1: "on"})
    return df


def hm(x=0, y=1, z=2, **kw):
    return series(y=y, x=x, colorColumn=f"__idx__{z}", **kw)


def build_new(tmp_path, plot_type, series_list, df, **plot):
    return Built(tmp_path, df=df, series_list=series_list, plot_type=plot_type, mutate=mutate_plot(**plot))


# ---------------------------------------------------------------- 設定（settings）


def test_new_types_accepted_and_plot_defaults():
    for t in NEW_TYPES:
        sl = [hm()] if t == "heatmap" else [series()]
        assert parse_settings(raw_settings(sl, plot_type=t)).plot.type == t
    d = parse_settings(raw_settings(plot_type="line")).plot
    assert (d.box_fliers, d.box_means, d.violin_medians, d.violin_means) == (True, False, True, False)
    raw = settings_module.default_settings()
    assert raw["plot"]["box"] == {"fliers": True, "means": False} and raw["plot"]["violin"] == {"medians": True, "means": False}
    assert settings_module.SCHEMA_VERSION == 4


def test_box_violin_options_validated_only_for_own_type():
    bad = {"box": {"fliers": "x", "means": 3}, "violin": {"medians": "x", "means": 3}}
    for t in ("line", "bar", "hist", "heatmap", "box", "violin"):
        sl = [hm()] if t == "heatmap" else [series()]
        if t == "box":
            bad2 = {"violin": bad["violin"]}
        elif t == "violin":
            bad2 = {"box": bad["box"]}
        else:
            bad2 = bad
        parse_settings(raw_settings(sl, plot_type=t, mutate=mutate_plot(**bad2)))  # 隠れているので、エラーにならない
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(plot_type="box", mutate=mutate_plot(box={"fliers": "x"})))
    assert e.value.field == "外れ値の点"
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(plot_type="violin", mutate=mutate_plot(violin={"medians": 3})))
    assert e.value.field == "中央値の線"
    s = parse_settings(raw_settings(plot_type="box", mutate=mutate_plot(box={"fliers": False, "means": True}))).plot
    assert (s.box_fliers, s.box_means) == (False, True)
    s = parse_settings(raw_settings(plot_type="violin", mutate=mutate_plot(violin={"medians": False, "means": True}))).plot
    assert (s.violin_medians, s.violin_means) == (False, True)


def test_heatmap_value_column_required_with_value_wording():
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series()], plot_type="heatmap"))
    assert str(e.value) == "系列1の値の列を選んでください。" and e.value.field == "系列1の値の列"
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series(colorColumn="abc")], plot_type="heatmap"))
    assert e.value.field == "系列1の値の列" and "値の列" in str(e.value)
    # 系列が2つ以上なら、系列ごとの値の列の検証より先に、系列の数のエラーを出す
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([hm(), series(colorColumn="abc")], plot_type="heatmap"))
    assert str(e.value).startswith("ヒートマップは系列1つで描きます。") and e.value.field == "系列"
    # scatterColor の文言は変えない
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([series()], plot_type="scatterColor"))
    assert e.value.field == "系列1の色分けの列"
    for t in ("box", "violin"):  # 使わない種類では要らない・検証しない
        assert parse_settings(raw_settings([series(colorColumn=5)], plot_type=t)).series[0].color_column == ""


def test_heatmap_colormap_used_and_validated_for_heatmap_only():
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([hm()], plot_type="heatmap", mutate=mutate_plot(colormap="nope")))
    assert e.value.field == "カラーマップ"
    s = parse_settings(raw_settings([hm()], plot_type="heatmap", mutate=mutate_plot(colormap="plasma", colorbarLabel=" 値 ")))
    assert (s.plot.colormap, s.plot.colorbar_label) == ("plasma", "値")
    for t in ("box", "violin"):
        parse_settings(raw_settings(plot_type=t, mutate=mutate_plot(colormap="nope")))


def test_new_types_hide_settings_and_keep_existing_rules():
    bad = {"marker": "zzz", "fill": {"lower": "x", "upper": ""}, "secondaryAxis": "yes", "errorBars": {"x": {"mode": "zzz"}, "y": {"mode": "zzz"}}}
    fit = [{"series": "s1", "model": "zzz"}]
    for t in NEW_TYPES:
        extra = {"colorColumn": "__idx__2"} if t == "heatmap" else {}
        s = parse_settings(raw_settings([series(**bad, **extra)], plot_type=t, fits=fit))
        sr = s.series[0]
        assert s.fits == () and sr.marker == "auto" and not sr.fill.enabled and sr.secondary_axis is False
        assert not sr.error_bars.y.enabled if hasattr(sr.error_bars.y, "enabled") else sr.error_bars.y.mode == "none"
        assert sr.error_bars.x.mode == "none"
    # 使う設定は従来どおり検証する（不透明度は3種類とも使う）
    for t in NEW_TYPES:
        extra = {"colorColumn": "__idx__2"} if t == "heatmap" else {}
        with pytest.raises(UserError):
            parse_settings(raw_settings([series(alpha=5, **extra)], plot_type=t))
    # box / violin は色・線幅を使う。線種・点サイズは使わない
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(color="zzz")], plot_type="box"))
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(lineWidth=0)], plot_type="violin"))
    parse_settings(raw_settings([series(lineStyle="zzz", markerSize="x")], plot_type="box"))
    parse_settings(raw_settings([series(lineStyle="zzz", markerSize="x")], plot_type="violin"))
    # heatmap は色・線幅・線種・点サイズを使わない（検証せず、既定の値）
    s = parse_settings(raw_settings([hm(color="zzz", lineWidth=-1, lineStyle="zzz", markerSize="x")], plot_type="heatmap")).series[0]
    assert (s.line_width, s.line_style, s.marker_size) == (2.0, "solid", None)
    # 既存の種類は従来どおり（色・線種は検証する）
    for t in ("line", "bar", "hist"):
        with pytest.raises(UserError):
            parse_settings(raw_settings([series(color="zzz")], plot_type=t))
        with pytest.raises(UserError):
            parse_settings(raw_settings([series(lineStyle="zzz")], plot_type=t))
    # X列（plot.xColumn）は新しい種類で使わない
    for t in NEW_TYPES:
        sl = [hm()] if t == "heatmap" else [series()]
        assert parse_settings(raw_settings(sl, plot_type=t, mutate=mutate_plot(xColumn="__idx__3"))).plot.x_column == ""
    assert parse_settings(raw_settings(plot_type="bar", mutate=mutate_plot(xColumn="__idx__3"))).plot.x_column == "__idx__3"


def test_python_rule_constants_are_consistent():
    S = settings_module
    assert set(S.XY_TYPES) == {"line", "step", "scatter", "scatterColor"}
    assert set(S.BOX_TYPES) == {"box", "violin"}
    assert set(S.NO_Y2_TYPES) == {"barh", "barStacked", "hist", "scatterColor", "box", "violin", "heatmap"}
    assert set(S.NO_Y_ERROR_TYPES) == {"barStacked", "hist", "box", "violin", "heatmap"}
    assert set(S.SERIES_X_TYPES) == set(S.XY_TYPES) | {"heatmap"}
    assert set(S.COLOR_COLUMN_TYPES) == {"scatterColor", "heatmap"}
    assert set(S.CATEGORY_BAR_TYPES) == {"bar", "barStacked", "barh"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
def test_js_chart_types_match_python_rules(tmp_path):
    """js/chart-types.js の述語が、settings.py の規則の定数と、全種類で一致する。"""
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp_path / "chart-types.js").write_text((REPO / "js/chart-types.js").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "run.mjs").write_text(
        """
        import * as m from "./chart-types.js";
        const out = {types: m.PLOT_TYPES};
        for (const t of m.PLOT_TYPES) {
          out[t] = {
            seriesX: m.usesSeriesX(t), globalX: m.usesGlobalX(t), marker: m.usesMarker(t), fill: m.usesFill(t), fits: m.usesFits(t),
            xErr: m.usesXErrors(t), yErr: m.usesYErrors(t), y2: m.usesY2(t), color: m.usesColorColumn(t), colormap: m.usesColormap(t),
            box: m.usesBox(t), violin: m.usesViolin(t), boxLike: m.isBoxLike(t), heatmap: m.isHeatmap(t),
          };
        }
        console.log(JSON.stringify(out));
        """,
        encoding="utf-8",
    )
    js = json.loads(subprocess.run(["node", "run.mjs"], cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30).stdout)
    S = settings_module
    assert set(js["types"]) == set(S.PLOT_TYPES)
    for t in S.PLOT_TYPES:
        r = js[t]
        assert r["seriesX"] == (t in S.SERIES_X_TYPES), t
        assert r["globalX"] == (t in S.CATEGORY_BAR_TYPES), t
        assert r["marker"] == r["fill"] == r["fits"] == r["xErr"] == (t in S.XY_TYPES), t
        assert r["yErr"] == (t not in S.NO_Y_ERROR_TYPES), t
        assert r["y2"] == (t not in S.NO_Y2_TYPES), t
        assert r["color"] == r["colormap"] == (t in S.COLOR_COLUMN_TYPES), t
        assert r["boxLike"] == (t in S.BOX_TYPES) and r["box"] == (t == "box") and r["violin"] == (t == "violin"), t
        assert r["heatmap"] == (t == "heatmap")


# ---------------------------------------------------------------- 箱ひげ図


def test_box_one_box_per_series_with_labels_and_positions(tmp_path):
    bt = build_new(tmp_path, "box", [series(y=0), series(y=1, label="B系列"), series(y=3)], dist_frame())

    def fn(fig):
        ax = fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == ["a [0]", "B系列", "one [3]"]
        assert ax.get_legend() is None and ax.get_xlim() == (-0.5, 2.5)

    s = bt.check(fn)
    assert s[0]["boxes"] == 3 and s[0]["violins"] == 0 and s[0]["meshes"] == 0
    assert s[0]["xlabel"] == "" and s[0]["ylabel"] == ""  # 系列が複数なら縦軸の自動ラベルは空
    assert s[0]["markers"] == [] and s[0]["alphas"] == [] and s[0]["drawstyles"] == []  # 箱ひげの線は系列の線に数えない
    assert s[0]["xscale"] == "linear" and s[0]["legend"] == []
    assert "tick_labels" not in bt.script.text and "vert=" not in bt.script.text


def test_box_values_style_fliers_means_and_numeric_cleaning(tmp_path):
    df = dist_frame()
    sl = [series(y=0, color="#00AA00", lineWidth=3.0, alpha=0.5), series(y=1)]
    bt = build_new(tmp_path, "box", sl, df)
    with bt.full() as run:
        ax = run.fig.axes[0]
        patches = [p for p in ax.patches if p.get_label() == "_box"]
        assert len(patches) == 2
        assert patches[0].get_alpha() == 0.5 and patches[0].get_linewidth() == 3.0
        assert matplotlib_color(patches[0].get_facecolor()[:3]) == "#00aa00" and matplotlib_color(patches[0].get_edgecolor()[:3]) == "#000000"
        meds = [ln for ln in ax.lines if ln.get_label() == "_box" and len(ln.get_xdata()) == 2 and ln.get_ydata()[0] == ln.get_ydata()[1] and abs(ln.get_xdata()[1] - ln.get_xdata()[0]) < 0.6 and ln.get_linewidth() == 3.0]
        assert meds and all(ln.get_color() == "black" for ln in meds)
        # 外れ値（15.0）が点として描かれる。NaN が混ざっても中央値は NaN にならない
        fliers = [ln for ln in ax.lines if ln.get_marker() == "o" and ln.get_label() == "_box"]
        assert any(15.0 in list(ln.get_ydata()) for ln in fliers)
        assert not any(np.isnan(np.asarray(ln.get_ydata(), dtype=float)).any() for ln in ax.lines)
    # 数値にできない値は警告（既存の形式）
    assert any(w["series"] == 2 and "数値に変換できない値が1件" in w["message"] and '"bad"' in w["message"] for w in bt.plan.warnings)
    assert bt.plan.warnings[0]["message"].startswith("系列2（b）:")
    # alpha 1 はコードに書かない
    assert '"alpha"' in bt.script.text and bt.script.text.count('"alpha"') == 1


def matplotlib_color(rgb):
    from matplotlib.colors import to_hex

    return to_hex(rgb)


def test_box_fliers_and_means_toggle(tmp_path):
    on = build_new(tmp_path, "box", [series(y=0)], dist_frame(), box={"fliers": True, "means": False})
    off = build_new(tmp_path, "box", [series(y=0)], dist_frame(), box={"fliers": False, "means": True})

    def counts(bt):
        with bt.full() as run:
            ax = run.fig.axes[0]
            fl = [ln for ln in ax.lines if ln.get_marker() == "o"]
            means = [ln for ln in ax.lines if ln.get_marker() == "D"]
            return sum(len(ln.get_xdata()) for ln in fl), len(means)

    assert counts(on)[0] >= 1 and counts(on)[1] == 0 and counts(off) == (0, 1)
    assert "showfliers=True" in on.script.text and "showmeans=True" in off.script.text
    on.check(lambda f: None)
    off.check(lambda f: None)


def test_box_empty_series_keeps_its_position_and_warns(tmp_path):
    bt = build_new(tmp_path, "box", [series(y=0), series(y=2), series(y=1)], dist_frame())
    assert any(w["series"] == 2 and "箱は描きません" in w["message"] for w in bt.plan.warnings)
    assert [p.has_points for p in bt.plan.series] == [True, False, True]
    assert "描ける値が無い" in bt.script.text

    def fn(fig):
        ax = fig.axes[0]
        assert ax.get_xlim() == (-0.5, 2.5)
        assert [t.get_text() for t in ax.get_xticklabels()] == ["a [0]", "c [2]", "b [1]"]
        centers = sorted(round(float((p.get_path().vertices[:, 0].min() + p.get_path().vertices[:, 0].max()) / 2), 3) for p in ax.patches if p.get_label() == "_box")
        assert centers == [0.0, 2.0]  # 2 つ目の位置は空いたまま

    assert bt.check(fn)[0]["boxes"] == 2


def test_box_no_values_at_all_is_error():
    with pytest.raises(UserError) as e:
        plan_of(df=dist_frame(), plot_type="box", series_list=[series(y=2)])
    assert "描画可能な数値データがありません" in str(e.value)


def test_box_datetime_y_is_error():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-01-02"]), "v": [1.0, 2.0]})
    for t in ("box", "violin"):
        with pytest.raises(UserError) as e:
            plan_of(df=df, plot_type=t, series_list=[series(y=0)])
        assert e.value.field == "系列1のY列" and "日時の列" in str(e.value)


def test_box_single_series_label_and_multiple_sources(tmp_path):
    bt = build_new(tmp_path, "box", [series(y=0)], dist_frame())
    s = bt.check(lambda f: None)
    assert s[0]["ylabel"] == "a [0]" and s[0]["xlabel"] == ""
    # データ元が違ってもよい（複数ファイル）
    from mplgui.dataprep import plan_plot

    sets = raw_settings([series(y=0), series(y=0, source="d2")], plot_type="box")
    sets["load"]["files"] = [{"id": "d1", "name": "a.csv", "sheet": ""}, {"id": "d2", "name": "b.csv", "sheet": ""}]
    st = parse_settings(sets)
    frames = {"d1": dist_frame(), "d2": dist_frame(seed=5)}
    plan = plan_plot(frames, st)
    assert [p.data_var for p in plan.series] == ["df1", "df2"]
    from mplgui.codegen import generate_script
    from mplgui.loader import load_file
    from mplgui.runner import figure_summary, run_script

    infos = {}
    for i, fid in enumerate(("d1", "d2")):
        (tmp_path / f"f{i}.csv").write_text(frames[fid].to_csv(index=False), encoding="utf-8")
        infos[fid] = load_file((tmp_path / f"f{i}.csv").read_bytes(), f"f{i}.csv", "", True).source
    script = generate_script(st, infos, plan)
    with run_script(script.auto_render_text(), injected={"df1": frames["d1"], "df2": frames["d2"]}) as run:
        assert figure_summary(run.fig)[0]["boxes"] == 2


def test_box_log_y_and_tick_step_and_annotation_index(tmp_path):
    df = pd.DataFrame({f"s{i}": [1.0 + i, 5, 20, 80 + i] for i in range(5)})
    sl = [series(y=i) for i in range(5)]

    def mutate(raw):
        raw["axes"]["y"]["scale"] = "log"
        raw["axes"]["x"]["majorStep"] = 2
        raw["axes"]["x"]["scale"] = "log"  # 横軸はカテゴリなので使わない
        raw["annotations"] = [
            {"kind": "vline", "x": "1.5", "label": "境目"},
            {"kind": "text", "text": "メモ", "x": "3", "y": "30"},
        ]

    bt = Built(tmp_path, df=df, series_list=sl, plot_type="box", mutate=mutate)
    s = bt.check(lambda f: None)
    assert s[0]["yscale"] == "log" and s[0]["xscale"] == "linear"
    assert [t for t in s[0]["xticklabels"] if t] == ["s0 [0]", "s2 [2]", "s4 [4]"]  # 2 個おき
    assert "tick_step = 2" in bt.script.text
    assert s[0]["annotations"]["vlines"] == 1 and s[0]["annotations"]["texts"] == 1
    assert s[0]["legend"] == ["境目"]  # 注釈の凡例名だけ。箱は凡例に出さない
    # 注釈の X は 0 始まりの番号。文字列は解釈できない
    with pytest.raises(UserError) as e:
        Built(tmp_path, df=df, series_list=sl, plot_type="box", mutate=lambda r: r.update(annotations=[{"kind": "vline", "x": "abc"}]))
    assert "注釈1" in str(e.value)


def test_box_axis_labels_override_and_title(tmp_path):
    def mutate(raw):
        raw["axes"]["x"]["label"] = "群"
        raw["axes"]["y"]["label"] = "値"

    bt = Built(tmp_path, df=dist_frame(), series_list=[series(y=0), series(y=1)], plot_type="box", mutate=mutate)
    s = bt.check(lambda f: None)
    assert (s[0]["xlabel"], s[0]["ylabel"]) == ("群", "値")


def test_box_tick_step_too_many_is_error():
    df = pd.DataFrame({"a": [1.0, 2, 3]})
    with pytest.raises(UserError):
        plan_of(df=df, plot_type="box", series_list=[series(y=0)], mutate=lambda r: r["axes"]["x"].update(majorStep=0.5))


# ---------------------------------------------------------------- バイオリン図


def test_violin_bodies_medians_means_and_colors(tmp_path):
    sl = [series(y=0, color="#0000FF", lineWidth=2.5, alpha=0.4), series(y=1)]
    bt = build_new(tmp_path, "violin", sl, dist_frame(), violin={"medians": True, "means": True})

    def fn(fig):
        ax = fig.axes[0]
        bodies = [c for c in ax.collections if c.get_label() == "_violin"]
        assert len(bodies) == 2
        assert bodies[0].get_alpha() == 0.4 and matplotlib_color(bodies[0].get_facecolor()[0][:3]) == "#0000ff"
        assert bodies[0].get_linewidth()[0] == 2.5
        assert [t.get_text() for t in ax.get_xticklabels()] == ["a [0]", "b [1]"]

    s = bt.check(fn)
    assert s[0]["violins"] == 2 and s[0]["boxes"] == 0 and s[0]["lines"] == 0 and s[0]["legend"] == []
    assert s[0]["collections"] == 2 + 2 * 5  # 胴 2 つ + (端 3 + 中央値 + 平均) × 2
    assert "vert=" not in bt.script.text


def test_violin_medians_off_and_means_off(tmp_path):
    bt = build_new(tmp_path, "violin", [series(y=0)], dist_frame(), violin={"medians": False, "means": False})
    s = bt.check(lambda f: None)
    assert s[0]["collections"] == 1 + 3  # 胴 + 端の線 3 つ
    assert "showmedians=False" in bt.script.text


def test_violin_needs_two_values(tmp_path):
    bt = build_new(tmp_path, "violin", [series(y=0), series(y=3), series(y=2)], dist_frame())
    msgs = [w["message"] for w in bt.plan.warnings]
    assert any("系列2" in m and "値が1個だけ" in m for m in msgs) and any("系列3" in m and "描きません" in m for m in msgs)
    s = bt.check(lambda f: None)
    assert s[0]["violins"] == 1 and s[0]["xlim"] == [-0.5, 2.5]
    with pytest.raises(UserError):
        plan_of(df=dist_frame(), plot_type="violin", series_list=[series(y=3)])  # 描ける系列が無い


# ---------------------------------------------------------------- ヒートマップ


def test_heatmap_numeric_grid_missing_cell_duplicates_and_colorbar(tmp_path):
    bt = build_new(tmp_path, "heatmap", [hm()], grid_frame(), colormap="plasma", colorbarLabel="温度 (℃)")
    assert any("1件重複" in w["message"] and w["series"] == 1 for w in bt.plan.warnings)

    def fn(fig):
        ax = fig.axes[0]
        mesh = [c for c in ax.collections if type(c).__name__ == "QuadMesh"][0]
        z = np.ma.filled(mesh.get_array().astype(float), np.nan).reshape(2, 3)
        assert np.allclose(z, [[2.0, np.nan, 6.0], [4.0, 5.0, 7.0]], equal_nan=True)  # (0,0) は 1 と 3 の平均。欠けたマスは NaN
        assert mesh.get_cmap().name == "plasma" and ax.get_legend() is None

    s = bt.check(fn)
    assert s[0]["meshes"] == 1 and s[0]["boxes"] == 0 and s[0]["violins"] == 0
    assert s[0]["colorbar"] == {"label": "温度 (℃)", "cmap": "plasma", "vmin": 2.0, "vmax": 7.0}
    assert (s[0]["xlabel"], s[0]["ylabel"]) == ("x", "y [1]") and len(s) == 1
    assert s[0]["xlim"] == [-0.5, 2.5] and s[0]["ylim"] == [-0.5, 1.5]
    assert 'shading="nearest"' in bt.script.text and "pivot_table" in bt.script.text and "alpha=" not in bt.script.text


def test_heatmap_default_colorbar_label_and_alpha(tmp_path):
    bt = build_new(tmp_path, "heatmap", [hm(alpha=0.5)], grid_frame())
    s = bt.check(lambda f: None)
    assert s[0]["colorbar"]["label"] == "z [2]" and s[0]["colorbar"]["cmap"] == "viridis"
    assert "alpha=0.5" in bt.script.text
    with bt.full() as run:
        mesh = [c for c in run.fig.axes[0].collections if type(c).__name__ == "QuadMesh"][0]
        assert mesh.get_alpha() == 0.5


def test_heatmap_text_axes_in_order_of_appearance_and_tick_step(tmp_path):
    df = grid_frame()
    bt = build_new(tmp_path, "heatmap", [hm(x=3, y=4)], df)

    def fn(fig):
        ax = fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == ["low", "mid", "high"]  # 現れた順（アルファベット順ではない）
        assert [t.get_text() for t in ax.get_yticklabels()] == ["off", "on"]

    s = bt.check(fn)
    assert s[0]["xlim"] == [-0.5, 2.5] and (s[0]["xlabel"], s[0]["ylabel"]) == ("tx", "ty [4]")

    wide = pd.DataFrame({"x": [f"c{i}" for i in range(10)] * 2, "y": ["r1"] * 10 + ["r2"] * 10, "z": np.arange(20.0)})
    bt = Built(tmp_path, df=wide, series_list=[hm()], plot_type="heatmap", mutate=lambda r: r["axes"]["x"].update(majorStep=3))
    s = bt.check(lambda f: None)
    assert [t for t in s[0]["xticklabels"] if t] == ["c0", "c3", "c6", "c9"] and "x_tick_step = 3" in bt.script.text


def test_heatmap_numeric_looking_text_axis_is_converted_with_warning(tmp_path):
    df = pd.DataFrame({"x": ["1", "2", "bad", "1", "2"], "y": [1.0, 1, 1, 2, 2], "z": [1.0, 2, 3, 4, 5]})
    bt = build_new(tmp_path, "heatmap", [hm()], df)
    assert any("X列" in w["message"] and "数値に変換できない値が1件" in w["message"] for w in bt.plan.warnings)
    s = bt.check(lambda f: None)
    assert s[0]["xlim"] == [0.5, 2.5]  # X は数値の軸（bad の行は除外）


def test_heatmap_value_column_warnings_and_errors():
    df = grid_frame()
    df["zs"] = ["1", "x", "3", "4", "5", "6"]
    plan = plan_of(df=df, plot_type="heatmap", series_list=[hm(z=5)])
    assert any("値の列" in w["message"] and "数値にできない値が1件" in w["message"] and "その行は使いません" in w["message"] for w in plan.warnings)
    df2 = grid_frame()
    df2["d"] = pd.to_datetime(["2024-01-01"] * 6)
    for kw, field_name in (({"z": 5}, "系列1の値の列"), ({"x": 5}, "系列1のX列"), ({"y": 5}, "系列1のY列")):
        with pytest.raises(UserError) as e:
            plan_of(df=df2, plot_type="heatmap", series_list=[hm(**kw)])
        assert e.value.field == field_name and "日時の列" in str(e.value)
    with pytest.raises(UserError) as e:
        plan_of(df=df, plot_type="heatmap", series_list=[hm(z=9)])
    assert e.value.field == "系列1の値の列" and "列" in str(e.value)
    with pytest.raises(UserError) as e:
        plan_of(df=df, plot_type="heatmap", series_list=[hm(), hm()])
    assert str(e.value).startswith("ヒートマップは系列1つで描きます。") and e.value.field == "系列"
    # 2つ目の系列の値の列が未選択でも、系列の数のエラーを先に出す（設定の検証の段階）
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings([hm(), series(colorColumn="")], plot_type="heatmap"))
    assert str(e.value).startswith("ヒートマップは系列1つで描きます。") and e.value.field == "系列"
    nan_z = pd.DataFrame({"x": [0, 1], "y": [0, 1], "z": ["a", "b"]})
    with pytest.raises(UserError) as e:
        plan_of(df=nan_z, plot_type="heatmap", series_list=[hm()])
    assert "描画可能な数値データがありません" in str(e.value)


def test_heatmap_size_limit():
    n = MAX_HEATMAP_SIZE
    ok = pd.DataFrame({"x": np.arange(n, dtype=float), "y": np.zeros(n), "z": np.ones(n)})
    assert plan_of(df=ok, plot_type="heatmap", series_list=[hm()]).heatmap.x_count == n
    big = pd.DataFrame({"x": np.arange(n + 1, dtype=float), "y": np.zeros(n + 1), "z": np.ones(n + 1)})
    with pytest.raises(UserError) as e:
        plan_of(df=big, plot_type="heatmap", series_list=[hm()])
    assert e.value.field == "系列1のX列" and f"{n + 1}種類" in str(e.value) and "X" in str(e.value)
    with pytest.raises(UserError) as e:
        plan_of(df=big[["y", "x", "z"]], plot_type="heatmap", series_list=[hm()])
    assert e.value.field == "系列1のY列" and "Y" in str(e.value)


def test_heatmap_single_row_column_log_axes_and_annotation(tmp_path):
    df = pd.DataFrame({"x": [1.0, 10, 100], "y": [1.0, 1, 1], "z": [1.0, 2, 3]})  # 1 行だけの格子

    def mutate(raw):
        raw["axes"]["x"]["scale"] = "log"
        raw["annotations"] = [{"kind": "vline", "x": "10"}]

    bt = Built(tmp_path, df=df, series_list=[hm()], plot_type="heatmap", mutate=mutate)
    s = bt.check(lambda f: None)
    assert s[0]["meshes"] == 1 and s[0]["xscale"] == "log" and s[0]["annotations"]["vlines"] == 1
    one = pd.DataFrame({"x": [3.0], "y": [4.0], "z": [5.0]})  # 1 マスだけ
    assert Built(tmp_path, df=one, series_list=[hm()], plot_type="heatmap").check(lambda f: None)[0]["meshes"] == 1


def test_heatmap_annotation_on_text_axis_is_index(tmp_path):
    def mutate(raw):
        raw["annotations"] = [{"kind": "vline", "x": "1"}, {"kind": "hline", "y": "0.5"}]

    bt = Built(tmp_path, df=grid_frame(), series_list=[hm(x=3, y=4)], plot_type="heatmap", mutate=mutate)
    s = bt.check(lambda f: None)
    assert s[0]["annotations"]["vlines"] == 1 and s[0]["annotations"]["hlines"] == 1
    # 日時の注釈は文字列の軸では使えない
    with pytest.raises(UserError):
        Built(tmp_path, df=grid_frame(), series_list=[hm(x=3, y=4)], plot_type="heatmap", mutate=lambda r: r.update(annotations=[{"kind": "vline", "x": "2024-01-01"}]))


def test_heatmap_legend_not_emitted_without_labelled_artists(tmp_path):
    bt = Built(tmp_path, df=grid_frame(), series_list=[hm(label="系列名")], plot_type="heatmap")
    assert "凡例に出せるラベルが無い" in bt.script.text
    assert bt.check(lambda f: None)[0]["legend"] == []


# ---------------------------------------------------------------- 共通

@pytest.mark.parametrize("plot_type", NEW_TYPES)
def test_new_types_full_and_auto_summaries_match(tmp_path, plot_type):
    if plot_type == "heatmap":
        bt = build_new(tmp_path, plot_type, [hm(x=3, y=1)], grid_frame())
    else:
        bt = build_new(tmp_path, plot_type, [series(y=0), series(y=1, label="B")], dist_frame())
    bt.check(lambda f: None)


@pytest.mark.parametrize("plot_type", NEW_TYPES)
def test_new_types_steps_and_axis_ranges(tmp_path, plot_type):
    bt = build_new(tmp_path, plot_type, [hm()] if plot_type == "heatmap" else [series(y=0)], grid_frame() if plot_type == "heatmap" else dist_frame())
    steps = bt.script.steps
    assert steps and all(s.message for s in steps)
    if plot_type == "heatmap":
        assert {"系列1の値の列", "カラーマップ"} <= {s.field for s in steps}
        assert any("ヒートマップ" in s.message for s in steps)
    else:
        assert any(s.message.startswith("グラフを描画できませんでした") for s in steps)


def test_existing_types_summaries_have_zero_new_keys(tmp_path):
    for t in ("line", "bar", "hist", "scatterColor"):
        sl = [colored()] if t == "scatterColor" else [series(y=1, x=4)]
        s = build(tmp_path, t, sl).check(lambda f: None)
        assert (s[0]["boxes"], s[0]["violins"], s[0]["meshes"]) == (0, 0, 0)


def test_injection_new_types(tmp_path):
    import ast

    evil = '"); import os; os.system("echo hi") #'
    label = "'''\n" + evil
    df = pd.DataFrame(
        {
            'c"\'\n' + evil: ["a", "b", "a", "b", "c"],
            "v" + evil: [1.0, 2, 3, 4, 5],
            "z" + evil: [1.0, 2, 3, 4, 6],
            "t" + evil: ["p", "q", "p", "q", "p"],
        }
    )
    cases = [
        ("box", [series(y=1, label=label), series(y=2, label=label)], {}),
        ("violin", [series(y=1, label=label), series(y=2, label=label)], {}),
        ("heatmap", [series(y=3, x=0, label=label, colorColumn="__idx__2")], {"colorbarLabel": label}),
    ]
    for plot_type, sl, plot in cases:
        bt = build_new(tmp_path, plot_type, sl, df, **plot)
        tree = ast.parse(bt.script.text)
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "system"]
        for line in bt.script.text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert "echo hi" not in line.split("  #")[0] or line.count('"') >= 2  # コードの中では文字列の内側にだけ現れる
        with bt.full() as run:
            assert run.fig is not None and "echo hi" not in run.output
        bt.check(lambda f: None)
    # 凡例名は目盛のラベルとしてリテラルに入る（柔軟な文字列でもそのまま読み戻せる）
    bt = build_new(tmp_path, "box", [series(y=1, label=label)], df)
    assert bt.check(lambda f: None)[0]["xticklabels"][0] == label
