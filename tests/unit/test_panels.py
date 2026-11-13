"""Phase 5e（G9 サブプロット）: パネルごとの計画・生成コード・図の要約。"""
import re

import numpy as np
import pandas as pd
import pytest
from style_helpers import Built, frame, raw_settings, series

from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot, panel_label
from mplgui.errors import UserError
from mplgui.loader import load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import parse_settings

# frame(): t=0 / v=1 / lo=2 / hi=3 / w=4（10 行）


def layout_mut(rows=2, cols=2, panels=None, title="", **layout):
    def mutate(raw):
        raw["plot"]["layout"].update(rows=rows, cols=cols, **layout)
        if panels is not None:
            raw["plot"]["panels"] = panels
        if title:
            raw["plot"]["title"] = title

    return mutate


def mut_all(*fns):
    def mutate(raw):
        for fn in fns:
            fn(raw)

    return mutate


def build(tmp_path, series_list, rows=2, cols=2, df=None, plot_type="line", mutate=None, panels=None, title="", annotations=None, fits=None, **layout):
    return Built(
        tmp_path, df=df, series_list=series_list, plot_type=plot_type, annotations=annotations, fits=fits,
        mutate=mut_all(layout_mut(rows, cols, panels, title, **layout), mutate or (lambda raw: None)),
    )


def summary(built):
    """全体の実行と自動描画用の実行の要約（一致も確かめる）。"""
    return built.check(lambda fig: None)


def plan(df=None, rows=2, cols=2, series_list=None, plot_type="line", mutate=None, panels=None, annotations=None, fits=None, **layout):
    loaded = load_file((df if df is not None else frame()).to_csv(index=False).encode("utf-8"), "d.csv", "", True)
    raw = raw_settings(
        series_list=series_list, plot_type=plot_type, annotations=annotations, fits=fits,
        mutate=mut_all(layout_mut(rows, cols, panels, "", **layout), mutate or (lambda raw: None)),
    )
    return plan_plot(loaded.df, parse_settings(raw))


def user_error(fn):
    with pytest.raises(UserError) as e:
        fn()
    return e.value


def axes_of(sm):
    """twin を除いた Axes の要約を、パネルの位置 [行, 列] で引く。"""
    out = {}
    for s in sm:
        out.setdefault(tuple(s["panel"]), s)
    return out


def twins(sm):
    seen, out = set(), []
    for s in sm:
        key = tuple(s["panel"])
        (out.append(s) if key in seen else seen.add(key))
    return out


# ---------------------------------------------------------------- 計画


def test_single_panel_plan_has_no_panels_and_code_is_single_axes(tmp_path):
    b = Built(tmp_path, series_list=[series(1), series(2)])
    assert b.plan.panels == () and not b.plan.layout.multi
    assert "axs" not in b.script.text and "plt.subplots(figsize=" in b.script.text
    assert "set_inverted" not in b.script.text


def test_panel_plans_keep_global_numbers_and_split_series():
    p = plan(series_list=[series(1), series(2, panel=1), series(3, panel=1), series(4, panel=3)])
    assert [pp.series_indices for pp in p.panels] == [(0,), (1, 2), (), (3,)]
    assert [pp.drawn for pp in p.panels] == [True, True, False, True]
    assert [s.number for s in p.panels[1].plan.series] == [2, 3]  # 系列N は図全体の番号
    assert [(pp.row, pp.col) for pp in p.panels] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert [s.number for s in p.series] == [1, 2, 3, 4] and p.plotted_count == 4
    assert [pp.label for pp in p.panels] == ["(a)", "(b)", "", "(d)"]  # 使わないパネルの記号は飛ぶ


@pytest.mark.parametrize(
    "style,expected",
    [("(a)", ["(a)", "(b)", "(c)"]), ("a", ["a", "b", "c"]), ("A", ["A", "B", "C"]), ("(A)", ["(A)", "(B)", "(C)"]), ("none", ["", "", ""])],
)
def test_panel_label_styles(style, expected):
    assert [panel_label(style, i) for i in range(3)] == expected


def test_per_panel_secondary_hist_and_colorbar_plans():
    p = plan(series_list=[series(1), series(2, panel=1, secondaryAxis=True)])
    assert [pp.plan.uses_secondary for pp in p.panels if pp.drawn] == [False, True]
    assert p.uses_secondary and p.panels[1].plan.y2_label == "lo [2]"
    h = plan(
        series_list=[series(1), series(4, panel=1)], plot_type="hist", rows=1, cols=2,
        mutate=lambda raw: raw["plot"]["hist"].update(bins=4),
    )
    assert [pp.plan.hist.bin_count for pp in h.panels] == [4, 4]
    c = plan(
        series_list=[series(1, colorColumn="__idx__4"), series(2, panel=1, colorColumn="__idx__3")],
        plot_type="scatterColor", rows=1, cols=2,
    )
    assert [pp.plan.colorbar.label for pp in c.panels] == ["w [4]", "hi [3]"]  # 色分けの列ごと（パネルごと）


def test_fit_text_order_is_counted_per_panel():
    fits = [{"series": s, "model": "linear", "show": "text"} for s in ("s1", "s2", "s3")]
    p = plan(
        series_list=[series(1, id="s1"), series(2, id="s2", panel=1), series(3, id="s3", panel=1)], fits=fits, rows=1, cols=2
    )
    assert [[f.text_index for f in pp.plan.fits] for pp in p.panels] == [[0], [0, 1]]
    assert [f.number for f in p.fits] == [1, 2, 3]  # 近似曲線N は図全体の番号


def test_annotation_numbers_are_global_and_unused_panel_warns():
    p = plan(
        series_list=[series(1), series(2, panel=1)],
        annotations=[{"kind": "hline", "y": "20", "panel": 1}, {"kind": "hline", "y": "21", "panel": 3}, {"kind": "hline", "y": "22"}],
    )
    assert [a.number for a in p.panels[1].plan.annotations] == [1]
    assert [a.number for a in p.panels[0].plan.annotations] == [3]
    assert [a.number for a in p.annotations] == [1, 3]
    assert {"series": 0, "message": "注釈2: パネル4に系列が無いため、描きません。"} in p.warnings


def test_no_drawable_data_error_names_the_panel():
    df = frame()
    df["bad"] = "x"
    e = user_error(lambda: plan(df=df, series_list=[series(1), series(5, panel=1)]))
    assert e.message.startswith("パネル2: 描画可能な数値データがありません。")
    e1 = user_error(lambda: plan(df=df, series_list=[series(5)], rows=1, cols=1))
    assert e1.message.startswith("描画可能な数値データがありません。")  # 1行×1列は今のまま


def test_kind_mismatch_between_panels():
    df = frame()
    df["name"] = [f"n{i}" for i in range(len(df))]
    e = user_error(lambda: plan(df=df, series_list=[series(1), series(1, x=5, panel=1)]))
    assert e.message == "パネルによって X の種類（数値・文字列）が違います。X軸の目盛の設定は全パネル共通なので、X列の種類をそろえてください。"
    assert e.field == "X列"
    # Y の種類（ヒートマップの Y が文字列の列と数値の列）
    grid = pd.DataFrame({"x": [0, 1, 0, 1], "yn": [0, 0, 1, 1], "ys": list("PPQQ"), "z": [1.0, 2.0, 3.0, 4.0]})
    e = user_error(
        lambda: plan(
            df=grid, plot_type="heatmap", rows=1, cols=2,
            series_list=[series(2, x=0, colorColumn="__idx__3"), series(1, x=0, colorColumn="__idx__3", panel=1)],
        )
    )
    assert e.message == "パネルによって Y の種類（数値・文字列）が違います。Y軸の目盛の設定は全パネル共通なので、Y列の種類をそろえてください。"
    assert e.field == "Y列"


def test_datetime_and_number_x_cannot_share_a_figure():
    df = frame()
    df["when"] = pd.date_range("2026-01-01", periods=len(df), freq="D").strftime("%Y-%m-%d")
    e = user_error(lambda: plan(df=df, series_list=[series(1), series(1, x=5, panel=1)]))
    assert e.message == "X が日時の系列と、日時でない系列を同じ図に描くことはできません。X列をそろえてください。"


def test_heatmap_per_panel_plans_two_heatmaps():
    grid = pd.DataFrame({"x": [0, 1, 0, 1], "y": [0, 0, 1, 1], "z": [1.0, 2.0, 3.0, 4.0], "z2": [5.0, 6.0, 7.0, 9.0]})
    p = plan(
        df=grid, plot_type="heatmap", rows=1, cols=2,
        series_list=[series(1, x=0, colorColumn="__idx__2"), series(1, x=0, colorColumn="__idx__3", panel=1)],
    )
    assert [pp.plan.heatmap.x_count for pp in p.panels] == [2, 2]
    assert [s.number for pp in p.panels for s in pp.plan.series] == [1, 2]


def test_sharing_only_for_number_log_datetime_axes():
    p = plan(series_list=[series(1), series(2, panel=1)], shareX=True, shareY=True)
    assert p.layout.share_x and p.layout.share_y
    q = plan(series_list=[series(1), series(2, panel=1)], plot_type="bar", rows=1, cols=2, shareX=True, shareY=True)
    assert not q.layout.share_x and q.layout.share_y  # 棒グラフの X はカテゴリ
    q = plan(series_list=[series(1), series(2, panel=1)], plot_type="box", rows=1, cols=2, shareX=True)
    assert not q.layout.share_x
    q = plan(series_list=[series(1), series(2, panel=1)], plot_type="barh", rows=1, cols=2, shareX=True, shareY=True)
    assert q.layout.share_x and not q.layout.share_y  # 横棒の Y はカテゴリ


# ---------------------------------------------------------------- 生成コードを実行した図


def test_series_land_on_their_panels_and_ax2_only_where_used(tmp_path):
    b = build(
        tmp_path,
        [series(1), series(2, panel=1, secondaryAxis=True), series(3, panel=1), series(4, panel=2)],
    )
    sm = summary(b)
    assert len(sm) == 5  # 4 つのパネル + 第2Y軸 1 つ
    panels = axes_of(sm)
    assert [panels[k]["lines"] for k in [(0, 0), (0, 1), (1, 0), (1, 1)]] == [1, 1, 1, 0]
    assert [s["panel"] for s in sm] == [[0, 0], [0, 1], [1, 0], [1, 1], [0, 1]]
    assert [s["panel"] for s in twins(sm)] == [[0, 1]]
    assert twins(sm)[0]["lines"] == 1
    assert panels[(1, 1)]["axison"] is False
    assert all(panels[k]["axison"] for k in [(0, 0), (0, 1), (1, 0)])
    assert b.script.text.count("twinx()") == 1


def test_per_panel_legends(tmp_path):
    b = build(
        tmp_path, [series(1, label="A"), series(2, label="B", panel=1), series(3, label="C", panel=1)], rows=1, cols=2,
    )
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["legend"] == ["A"] and panels[(0, 1)]["legend"] == ["B", "C"]


def test_second_axis_legend_is_per_panel(tmp_path):
    b = build(tmp_path, [series(1, label="A"), series(2, label="B", panel=1, secondaryAxis=True), series(3, label="C", panel=1)], rows=1, cols=2)
    sm = summary(b)
    assert axes_of(sm)[(0, 1)]["legend"] == ["C", "B"] or axes_of(sm)[(0, 1)]["legend"] == ["B", "C"]
    assert axes_of(sm)[(0, 0)]["legend"] == ["A"]


def test_annotations_land_on_their_panels(tmp_path):
    b = build(
        tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2,
        annotations=[{"kind": "hline", "y": "20", "panel": 1}, {"kind": "vline", "x": "3"}, {"kind": "text", "text": "T", "x": "1", "y": "12", "panel": 1}],
    )
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["annotations"] == {"texts": 0, "hlines": 0, "vlines": 1, "hspans": 0, "vspans": 0}
    assert panels[(0, 1)]["annotations"] == {"texts": 1, "hlines": 1, "vlines": 0, "hspans": 0, "vspans": 0}


def test_annotation_only_panel_is_not_drawn_and_warns(tmp_path):
    b = build(tmp_path, [series(1)], rows=1, cols=2, annotations=[{"kind": "hline", "y": "20", "panel": 1}])
    panels = axes_of(summary(b))
    assert panels[(0, 1)]["axison"] is False and panels[(0, 1)]["annotations"]["hlines"] == 0
    assert any("注釈1: パネル2に系列が無いため、描きません。" in w["message"] for w in b.plan.warnings)


def test_fit_text_and_legend_are_per_panel(tmp_path):
    fits = [{"series": "s1", "model": "linear", "show": "text"}, {"series": "s2", "model": "linear", "show": "text"}]
    b = build(tmp_path, [series(1, id="s1"), series(2, id="s2", panel=1)], rows=1, cols=2, fits=fits)
    with b.full() as run:
        ax0, ax1 = run.fig.axes[:2]
        ys = [[t.get_position()[1] for t in ax.texts] for ax in (ax0, ax1)]
        assert ys == [[0.97], [0.97]]  # どちらのパネルも左上から並ぶ
    sm = summary(b)
    assert [axes_of(sm)[k]["fittexts"] for k in [(0, 0), (0, 1)]] == [1, 1]


def test_scatter_color_has_a_colorbar_per_panel(tmp_path):
    b = build(
        tmp_path, [series(1, colorColumn="__idx__4"), series(2, panel=1, colorColumn="__idx__4")], rows=1, cols=2,
        plot_type="scatterColor",
    )
    sm = summary(b)
    assert len(sm) == 2  # カラーバーの Axes は一覧に入れない
    cbs = [s["colorbar"] for s in sm]
    assert all(cb is not None for cb in cbs) and cbs[0]["label"] == "w [4]"
    assert b.script.text.count("fig.colorbar(") == 2 and b.script.text.count("color_norm = plt.Normalize()") == 2
    df = frame()
    df["c"] = df["t"] * 100
    b2 = build(
        tmp_path, [series(1, colorColumn="__idx__4"), series(2, panel=1, colorColumn="__idx__5")], rows=1, cols=2,
        plot_type="scatterColor", df=df,
    )
    sm2 = summary(b2)
    assert sm2[0]["colorbar"]["vmax"] == pytest.approx(100 - 0 * 3.0)  # w の最大
    assert sm2[1]["colorbar"]["vmax"] == pytest.approx(900.0)  # 色の範囲はパネルごと


def test_hist_bins_are_per_panel(tmp_path):
    df = pd.DataFrame({"a": np.arange(20.0), "b": np.arange(20.0) * 100})
    b = build(
        tmp_path, [series(0, id="s1"), series(1, id="s2", panel=1)], rows=1, cols=2, df=df, plot_type="hist",
        mutate=lambda raw: raw["plot"]["hist"].update(bins=5),
    )
    sm = summary(b)
    panels = axes_of(sm)
    assert [panels[k]["bars"]["vertical"] for k in [(0, 0), (0, 1)]] == [5, 5]
    assert panels[(0, 0)]["xlim"][1] < 100 < panels[(0, 1)]["xlim"][1]  # 区間もパネルごと
    assert b.script.text.count("np.histogram_bin_edges(") == 2


def test_box_positions_are_per_panel(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=1)], rows=1, cols=2, plot_type="box")
    panels = axes_of(summary(b))
    assert [panels[k]["boxes"] for k in [(0, 0), (0, 1)]] == [1, 2]
    assert panels[(0, 0)]["xlim"] == [-0.5, 0.5] and panels[(0, 1)]["xlim"] == [-0.5, 1.5]
    assert [t for t in panels[(0, 1)]["xticklabels"]] == ["lo [2]", "hi [3]"]


def test_violin_per_panel(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, plot_type="violin")
    panels = axes_of(summary(b))
    assert [panels[k]["violins"] for k in [(0, 0), (0, 1)]] == [1, 1]


def test_bar_and_stacked_per_panel(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=1), series(4)], rows=1, cols=2, plot_type="bar")
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["bars"]["containers"] == [10, 10] and panels[(0, 1)]["bars"]["containers"] == [10, 10]
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=1)], rows=1, cols=2, plot_type="barStacked")
    panels = axes_of(summary(b))
    assert panels[(0, 1)]["bars"]["stacked"] == 1 and panels[(0, 0)]["bars"]["stacked"] == 0


@pytest.mark.parametrize("plot_type", ["bar", "barh"])
def test_bar_panels_with_different_series_counts_draw(tmp_path, plot_type):
    # パネルが2つ以上のときは、1系列の棒も位置の形（カテゴリ）で描くので、系列の数が違っても種類はそろう
    b = build(tmp_path, [series(1), series(2), series(3, panel=1)], rows=2, cols=1, plot_type=plot_type)
    assert b.plan.panels[0].plan.axes.x.kind == b.plan.panels[1].plan.axes.x.kind
    key = "horizontal" if plot_type == "barh" else "vertical"
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["bars"]["containers"] == [10, 10] and panels[(1, 0)]["bars"]["containers"] == [10]
    assert panels[(1, 0)]["bars"][key] == 10
    assert "positions + offset" in b.script.text and b.script.text.count("positions = np.arange") == 2


def test_single_series_bar_panel_uses_category_form_with_error_bars(tmp_path):
    err = {"y": {"mode": "fixed", "value": 1.0}}
    b = build(tmp_path, [series(1, errorBars=err), series(2, panel=1)], rows=1, cols=2, plot_type="bar")
    text = b.script.text
    assert "width = 0.8 / 1" in text and "yerr=" in text and "set_xticks(positions[::tick_step])" in text
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["bars"]["vertical"] == 10 and panels[(0, 0)]["xlim"][0] < 0  # 位置 0, 1, …（行番号ではなくカテゴリ）
    b = build(tmp_path, [series(1, errorBars=err), series(2, panel=1)], rows=1, cols=2, plot_type="barh")
    assert "xerr=" in b.script.text and summary(b)


def test_single_series_bar_panel_annotation_x_is_a_category_index(tmp_path):
    ann = [{"kind": "vline", "x": "2", "panel": 1}, {"kind": "text", "text": "T", "x": "1.5", "y": "5", "panel": 1}]
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, plot_type="bar", annotations=ann)
    p1 = b.plan.panels[1].plan
    assert p1.axes.x.kind == "category" and [a.x for a in p1.annotations] == [2.0, 1.5]  # 何番目のカテゴリか
    assert axes_of(summary(b))[(0, 1)]["annotations"]["vlines"] == 1
    # 日時の X も、今までどおりカテゴリの文字列にする
    df = pd.DataFrame({"d": pd.date_range("2026-01-01", periods=4, freq="D"), "v": [1.0, 2.0, 3.0, 4.0], "w": [4.0, 3.0, 2.0, 1.0]})
    b = build(tmp_path, [series(1, x=0), series(2, x=0, panel=1)], rows=1, cols=2, plot_type="bar", df=df, mutate=lambda raw: raw["plot"].update(xColumn="__idx__0"))
    assert axes_of(summary(b))[(0, 1)]["xticklabels"] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]


def test_single_panel_bar_is_unchanged(tmp_path):
    b = Built(tmp_path, series_list=[series(1)], plot_type="bar")
    assert not b.plan.bar_positions and "positions" not in b.script.text


def test_heatmap_per_panel_with_colorbars(tmp_path):
    grid = pd.DataFrame({"x": [0, 1, 0, 1], "y": [0, 0, 1, 1], "z": [1.0, 2.0, 3.0, 4.0], "z2": [5.0, 6.0, 7.0, 9.0]})
    b = build(
        tmp_path, [series(1, x=0, colorColumn="__idx__2"), series(1, x=0, colorColumn="__idx__3", panel=1)], rows=1, cols=2,
        df=grid, plot_type="heatmap",
    )
    sm = summary(b)
    assert [s["meshes"] for s in sm] == [1, 1]
    assert [(s["colorbar"]["vmin"], s["colorbar"]["vmax"]) for s in sm] == [(1.0, 4.0), (5.0, 9.0)]


def test_hidden_panels_are_turned_off(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=3)], rows=2, cols=2)
    panels = axes_of(summary(b))
    assert [panels[k]["axison"] for k in [(0, 0), (0, 1), (1, 0), (1, 1)]] == [True, False, False, True]
    assert panels[(0, 1)]["titleleft"] == "" and panels[(1, 0)]["titleleft"] == ""  # 記号も付けない
    assert b.script.text.count('.axis("off")') == 2 and "# ==== 6. 使わないパネル ====" in b.script.text


@pytest.mark.parametrize(
    "style,expected", [("(a)", ["(a)", "(b)", "(d)"]), ("a", ["a", "b", "d"]), ("A", ["A", "B", "D"]), ("(A)", ["(A)", "(B)", "(D)"]), ("none", ["", "", ""])]
)
def test_label_styles_follow_panel_position(tmp_path, style, expected):
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=3)], labelStyle=style)
    panels = axes_of(summary(b))
    assert [panels[k]["titleleft"] for k in [(0, 0), (0, 1), (1, 1)]] == expected
    assert panels[(1, 0)]["titleleft"] == ""


def test_label_bold_and_default_weight(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, labelBold=True)
    with b.full() as run:
        assert run.fig.axes[0]._left_title.get_fontweight() == "bold"
    assert 'loc="left", fontsize=FONT_SIZE + 2, fontweight="bold")' in b.script.text
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2)
    with b.full() as run:
        assert run.fig.axes[0]._left_title.get_fontweight() == "normal"
    assert "fontweight" not in b.script.text


def test_suptitle_and_panel_titles(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, title="全体", panels=[{"title": "左"}, {"title": "右"}])
    sm = summary(b)
    assert [s["suptitle"] for s in sm] == ["全体", ""]
    assert [s["title"] for s in sm] == ["左", "右"]
    assert "fig.suptitle(" in b.script.text
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2)
    assert "suptitle" not in b.script.text and [s["suptitle"] for s in summary(b)] == ["", ""]


def test_axis_label_precedence_panel_then_global_then_auto(tmp_path):
    b = build(
        tmp_path, [series(1), series(2, panel=1), series(3, panel=2)], rows=3, cols=1,
        panels=[{"xLabel": "P0", "yLabel": "Y0"}, {"xLabel": "", "yLabel": ""}, {}],
        mutate=lambda raw: raw["axes"]["y"].update(label="全体のY"),
    )
    panels = axes_of(summary(b))
    assert [panels[(r, 0)]["xlabel"] for r in range(3)] == ["P0", "t", "t"]  # パネル → 全体（無い）→ 自動
    assert [panels[(r, 0)]["ylabel"] for r in range(3)] == ["Y0", "全体のY", "全体のY"]


def test_sharing_labels_inversion_and_tick_numbers(tmp_path):
    def mutate(raw):
        raw["axes"]["x"].update(inverted=True)
        raw["axes"]["y"].update(inverted=True)

    b = build(
        tmp_path, [series(1), series(2, panel=1), series(3, panel=2), series(4, panel=3)], shareX=True, shareY=True, mutate=mutate,
    )
    sm = summary(b)
    panels = axes_of(sm)
    assert all(s["xinverted"] and s["yinverted"] for s in sm)  # 反転は1回だけ効く
    assert [panels[k]["xlabel"] for k in [(0, 0), (0, 1), (1, 0), (1, 1)]] == ["", "", "t", "t"]  # 外側（各列の一番下）だけ
    assert [bool(panels[k]["ylabel"]) for k in [(0, 0), (0, 1), (1, 0), (1, 1)]] == [True, False, True, False]  # 外側（各行の一番左）だけ
    assert panels[(0, 0)]["xlim"] == panels[(1, 1)]["xlim"] and panels[(0, 0)]["ylim"] == panels[(1, 1)]["ylim"]
    assert b.script.text.count(".xaxis.set_inverted(True)") == 4 and "invert_xaxis" not in b.script.text
    assert "sharex=True, sharey=True" in b.script.text


def test_inversion_without_sharing_also_set_inverted(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, mutate=lambda raw: raw["axes"]["x"].update(inverted=True))
    assert all(s["xinverted"] for s in summary(b))
    single = Built(tmp_path, series_list=[series(1)], mutate=lambda raw: raw["axes"]["x"].update(inverted=True))
    assert "ax.invert_xaxis()" in single.script.text  # 1行×1列は今のまま


def test_tick_numbers_return_when_bottom_panel_is_unused(tmp_path):
    def tick_labels_visible(fig):
        return [bool(ax.xaxis.get_major_ticks()[0].label1.get_visible()) for ax in fig.axes if ax.axison]

    # 2×2、X を共有。(1, 1) が空: 列 1 の一番下は (0, 1)
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=2)], shareX=True)
    with b.full() as run:
        run.fig.canvas.draw()
        assert tick_labels_visible(run.fig) == [False, True, True]
        sm = figure_summary(run.fig)
    panels = axes_of(sm)
    assert panels[(0, 1)]["xlabel"] == "t" and panels[(0, 0)]["xlabel"] == "" and panels[(1, 0)]["xlabel"] == "t"
    assert 'ax.tick_params(axis="x", labelbottom=True)' in b.script.text
    summary(b)  # 自動描画用との一致
    # 一番下のパネルを使うときは出し直さない
    b = build(tmp_path, [series(1), series(2, panel=1), series(3, panel=2), series(4, panel=3)], shareX=True)
    assert "labelbottom=True" not in b.script.text


def test_sharing_is_not_applied_to_category_axes(tmp_path):
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, plot_type="box", shareX=True)
    assert "sharex" not in b.script.text
    panels = axes_of(summary(b))
    assert panels[(0, 0)]["xlabel"] == panels[(0, 1)]["xlabel"] == ""


def test_margins_all_four_sides_still_tighten_first(tmp_path):
    def mutate(raw):
        raw["plot"]["margins"] = {"left": 0.1, "right": 0.9, "bottom": 0.2, "top": 0.8}

    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2, mutate=mutate)
    text = b.script.text
    assert text.index("fig.tight_layout()") < text.index("fig.subplots_adjust(")
    with b.full() as run:
        sp = run.fig.subplotpars
        assert (sp.left, sp.right, sp.bottom, sp.top) == (0.1, 0.9, 0.2, 0.8)
    b = build(tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2)
    assert "fig.tight_layout()" in b.script.text and "subplots_adjust" not in b.script.text
    # 1行×1列は、4辺を指定したとき tight_layout を呼ばない（今のまま）
    single = Built(tmp_path, series_list=[series(1)], mutate=mutate)
    assert "tight_layout" not in single.script.text


def test_one_panel_per_cell_all_sixteen(tmp_path):
    b = build(tmp_path, [series(1, panel=i) for i in range(16)], rows=4, cols=4)
    sm = summary(b)
    assert len(sm) == 16 and [s["panel"] for s in sm] == [[r, c] for r in range(4) for c in range(4)]


def test_imports_are_written_once_for_all_panels(tmp_path):
    df = pd.DataFrame(
        {"d": pd.date_range("2026-01-01", periods=5, freq="D"), "v": [1.0, 2.0, 3.0, 4.0, 5.0], "e": [0.1] * 5, "w": [5.0, 4.0, 3.0, 2.0, 1.0]}
    )
    df.to_csv(tmp_path / "d.csv", index=False)
    b = build(
        tmp_path, [series(1, x=0, errorBars={"y": {"mode": "fixed", "value": 0.2}}), series(3, x=0, panel=1)], rows=1, cols=2, df=df,
        shareX=True,
    )
    text = b.script.text
    assert text.count("import matplotlib.dates as mdates") == 1 and text.count("def draw_error_bars") == 1
    sm = summary(b)
    assert all(s["xconverter"] is not None for s in sm)


def test_full_and_auto_render_summaries_match_on_complex_figure(tmp_path):
    fits = [{"series": "s1", "model": "poly", "degree": 2, "show": "legend"}]
    b = build(
        tmp_path,
        [series(1, id="s1", fill={"lower": "__idx__2", "upper": "__idx__3"}), series(2, panel=1, secondaryAxis=True), series(3, panel=1), series(4, panel=3)],
        title="図", panels=[{"title": "A"}, {"title": "B", "y2Label": "第2"}], fits=fits,
        annotations=[{"kind": "hspan", "start": "10", "end": "20", "panel": 3}, {"kind": "vline", "x": "2", "panel": 1}],
        shareX=True, labelBold=True,
    )
    sm = summary(b)
    assert axes_of(sm)[(1, 1)]["annotations"]["hspans"] == 1 and axes_of(sm)[(0, 1)]["annotations"]["vlines"] == 1
    assert axes_of(sm)[(0, 0)]["bands"] == 1 and axes_of(sm)[(0, 0)]["fitlines"] == 1


def test_error_steps_map_into_panels(tmp_path):
    b = build(
        tmp_path, [series(1), series(2, panel=1)], rows=1, cols=2,
        annotations=[{"kind": "hline", "y": "20", "panel": 1}],
    )
    steps = {s.field for s in b.script.steps if s.field}
    assert "注釈1" in steps and "余白" in steps
    ann_step = next(s for s in b.script.steps if s.field == "注釈1")
    lines = b.script.text.split("\n")
    heading = max(i for i, ln in enumerate(lines[: ann_step.start]) if ln.startswith("# ==== "))
    assert "パネル2" in lines[heading]  # 注釈1 の手順は、パネル2 の節の中


# ---------------------------------------------------------------- 安全性


def test_panel_strings_are_not_injected(tmp_path):
    evil = 'x"""\n__import__("os").system("echo hacked")  # \\'
    evil2 = "'; raise SystemExit(7) #"
    b = build(
        tmp_path, [series(1), series(2, panel=1, secondaryAxis=True)], rows=1, cols=2, title=evil,
        panels=[{"title": evil, "xLabel": evil2, "yLabel": evil}, {"title": evil2, "xLabel": evil, "yLabel": evil2, "y2Label": evil}],
    )
    sm = summary(b)
    panels = axes_of(sm)
    assert panels[(0, 0)]["title"] == evil and panels[(0, 1)]["title"] == evil2
    assert panels[(0, 0)]["xlabel"] == evil2 and panels[(0, 1)]["ylabel"] == evil2
    assert twins(sm)[0]["ylabel"] == evil
    assert sm[0]["suptitle"] == evil
    for line in b.script.text.split("\n"):  # 改行を含む文字列がコードの行になっていない
        assert "hacked" not in line or line.lstrip().startswith(("ax", "fig"))
    assert not any(line.startswith("__import__") for line in b.script.text.split("\n"))
