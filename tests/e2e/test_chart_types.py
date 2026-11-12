"""グラフの種類（Phase 5c, G7）: step / barh / 積み上げ棒 / ヒストグラム / 色分け散布図。
種類ごとの欄の出し分け（隠した値は残る）、図の要約（data-summary）、軸の種類（barh の縦軸）、エラーと復帰。"""
import pytest

from helpers import (
    add_annotation,
    add_files,
    code_is_stale,
    code_text,
    enter_edit_mode,
    image_generation,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    open_tick_group,
    plot_settings,
    series_state,
    set_axis_option,
    set_plot_type,
    status_kind,
    status_text,
    visible_ids,
    wait_app_ready,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

CAT, A, B, C, ERR, M = (f"__idx__{i}" for i in range(6))


def start(page, app_url, fixtures_dir, plot_type=None, x=None, y=A):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "chart_types.csv")
    wait_settled(page)
    if plot_type:
        set_plot_type(page, plot_type)
    if x:
        page.select_option("#series-s1-x", x)
    if y:
        page.select_option("#series-s1-y", y)
    wait_settled(page)


def axis0(page):
    return image_summary(page)[0]


def test_type_options_keep_existing_labels_and_add_new(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    options = page.eval_on_selector_all("#plotType option", "els => els.map(e => [e.value, e.textContent.trim()])")
    assert options[:3] == [["line", "line"], ["scatter", "scatter"], ["bar", "bar"]]
    assert options[3:] == [
        ["step", "step"], ["barh", "barh（横棒）"], ["barStacked", "bar（積み上げ）"],
        ["hist", "hist（ヒストグラム）"], ["scatterColor", "scatter（色分け）"],
    ]
    labels = page.eval_on_selector_all("#colorMap option", "els => els.map(e => e.value)")
    assert labels == ["viridis", "cividis", "plasma", "inferno", "magma", "coolwarm", "RdBu_r", "gray"]


GROUP_IDS = ["stepGroup", "histGroup", "colorMapGroup", "yScaleGroup", "globalXGroup", "addFitBtn", "fitList", "addAnnotationBtn"]
CARD_IDS = [
    "series-s1-x", "series-s1-marker", "series-s1-marker-size", "series-s1-errorbars", "series-s1-xerr-mode", "series-s1-yerr-mode",
    "series-s1-fill", "series-s1-use-y2", "series-s1-color-column", "series-s1-line-width", "series-s1-alpha",
]
BAR_LIKE = dict(globalXGroup=False, addFitBtn=False, fitList=False, addAnnotationBtn=True)
XY = dict(globalXGroup=False, addFitBtn=True, fitList=True, addAnnotationBtn=True)
# 種類 → 出ている要素（書いていない要素は出ていない）
EXPECTED = {
    "line": {**XY, "series-s1-x": 1, "series-s1-marker": 1, "series-s1-marker-size": 1, "series-s1-errorbars": 1, "series-s1-xerr-mode": 1,
             "series-s1-yerr-mode": 1, "series-s1-fill": 1, "series-s1-use-y2": 1},
    "step": {**XY, "stepGroup": 1, "series-s1-x": 1, "series-s1-marker": 1, "series-s1-marker-size": 1, "series-s1-errorbars": 1,
             "series-s1-xerr-mode": 1, "series-s1-yerr-mode": 1, "series-s1-fill": 1, "series-s1-use-y2": 1},
    "scatter": {**XY, "series-s1-x": 1, "series-s1-marker": 1, "series-s1-marker-size": 1, "series-s1-errorbars": 1, "series-s1-xerr-mode": 1,
                "series-s1-yerr-mode": 1, "series-s1-fill": 1, "series-s1-use-y2": 1},
    "scatterColor": {**XY, "colorMapGroup": 1, "series-s1-x": 1, "series-s1-marker": 1, "series-s1-marker-size": 1, "series-s1-errorbars": 1,
                     "series-s1-xerr-mode": 1, "series-s1-yerr-mode": 1, "series-s1-fill": 1, "series-s1-color-column": 1},
    "bar": {**BAR_LIKE, "globalXGroup": True, "series-s1-errorbars": 1, "series-s1-yerr-mode": 1, "series-s1-use-y2": 1},
    "barh": {**BAR_LIKE, "globalXGroup": True, "yScaleGroup": False, "series-s1-errorbars": 1, "series-s1-yerr-mode": 1},
    "barStacked": {**BAR_LIKE, "globalXGroup": True},
    "hist": {**BAR_LIKE, "histGroup": 1},
}


@pytest.mark.parametrize("plot_type", list(EXPECTED))
def test_visibility_per_type(plot_type, page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    page.evaluate("document.getElementById('series-s1-errorbars').open = true")
    set_plot_type(page, plot_type)
    want = EXPECTED[plot_type]
    got = visible_ids(page, GROUP_IDS + CARD_IDS)
    always = {"series-s1-line-width", "series-s1-alpha", "addAnnotationBtn", "yScaleGroup"}  # 種類によらず出る（barh の Y スケールだけ隠す）
    for element_id, shown in got.items():
        assert shown == bool(want.get(element_id, element_id in always)), f"{plot_type}: {element_id} shown={shown}"
    note_shown = not is_hidden_by_id(page, "fitBarNote")
    assert note_shown == (plot_type in ("bar", "barh", "barStacked", "hist"))
    if note_shown:
        assert "ヒストグラム" in page.inner_text("#fitBarNote")


def test_hidden_values_are_kept_when_switching_type(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="step")
    page.select_option("#stepWhere", "mid")
    set_plot_type(page, "hist")
    page.fill("#histBins", "7")
    page.check("#histDensity")
    set_plot_type(page, "scatterColor")
    page.select_option("#colorMap", "plasma")
    page.fill("#colorbarLabel", "電流")
    page.select_option("#series-s1-color-column", C)
    set_plot_type(page, "line")
    assert is_hidden_by_id(page, "stepGroup") and is_hidden_by_id(page, "histGroup") and is_hidden_by_id(page, "colorMapGroup")
    plot = plot_settings(page)
    assert plot["step"]["where"] == "mid" and plot["hist"] == {"bins": 7, "density": True}
    assert plot["colormap"] == "plasma" and plot["colorbarLabel"] == "電流"
    assert series_state(page, "s1")["colorColumn"] == C
    set_plot_type(page, "step")
    assert page.input_value("#stepWhere") == "mid"
    assert axis0(page)["drawstyles"] == ["steps-mid"]
    set_plot_type(page, "hist")
    assert page.input_value("#histBins") == "7" and page.is_checked("#histDensity")
    set_plot_type(page, "scatterColor")
    assert page.input_value("#series-s1-color-column") == C and page.input_value("#colorMap") == "plasma"


def test_step_renders_drawstyle_and_follows_where(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="step", x="__idx__1", y=B)
    assert axis0(page)["drawstyles"] == ["steps-post"]
    previous = image_generation(page)
    page.select_option("#stepWhere", "pre")
    wait_settled(page)
    assert axis0(page)["drawstyles"] == ["steps-pre"] and image_generation(page) != previous
    wait_code_generated(page)
    assert 'drawstyle="steps-pre"' in code_text(page)


def test_barh_summary_labels_and_y_tick_step(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="barh", y=A)
    page.select_option("#xColumn", CAT)
    wait_settled(page)
    s = axis0(page)
    assert s["bars"]["horizontal"] == 12 and s["bars"]["vertical"] == 0
    assert s["xlabel"] == "a [1]" and s["ylabel"] == "category"  # 軸ラベルの自動の値が入れ替わる
    # 縦軸はカテゴリ: Y のスケールは隠れ、目盛は「何個おき」
    assert is_hidden_by_id(page, "yScaleGroup")
    open_tick_group(page, "y")
    assert "何個おきに" in page.inner_text("#yMajorStepHelp")
    assert is_hidden_by_id(page, "yMinorGroup") and is_hidden_by_id(page, "yTickFormatGroup")
    assert not is_hidden_by_id(page, "xTickFormatGroup")  # 横軸は数値
    set_axis_option(page, "#yMajorStep", "3")
    s = axis0(page)
    assert s["ymajor"] == "MultipleLocator"
    assert len([t for t in s["yticklabels"] if t]) in (4, 5)
    wait_code_generated(page)
    # 注釈の Y は何番目のカテゴリか
    ann = add_annotation(page, "hline", y="2")
    wait_settled(page)
    assert page.get_attribute(f"#annotation-{ann}-y", "placeholder") == "何番目か（0 始まり）"
    assert axis0(page)["annotations"]["hlines"] == 1
    # 横軸（数値）の注釈は数値の例のまま
    vl = add_annotation(page, "vline", x="3")
    assert page.get_attribute(f"#annotation-{vl}-x", "placeholder") == "例 1.5"
    # 第2Y軸は使えない（値は残るが、欄を隠す）
    assert is_hidden_by_id(page, "series-s1-use-y2")


def test_barh_numeric_single_series_y_axis_is_numeric(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="barh", y=A)
    page.select_option("#xColumn", B)  # 数値の X 列 + 1 系列: 縦軸は数値
    wait_settled(page)
    open_tick_group(page, "y")
    assert "何個おきに" not in page.inner_text("#yMajorStepHelp")
    assert not is_hidden_by_id(page, "yTickFormatGroup")


def test_stacked_bar_with_negative_values(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="barStacked", y=A)
    page.select_option("#xColumn", CAT)
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", B)  # 正負が混ざる列
    wait_settled(page)
    s = axis0(page)
    assert s["bars"]["vertical"] == 24 and s["bars"]["stacked"] == 1 and s["bars"]["containers"] == [12, 12]
    assert not is_hidden_by_id(page, "xColumn")
    assert is_hidden_by_id(page, "series-s2-errorbars") and is_hidden_by_id(page, "series-s2-use-y2")
    assert s["ylim"][0] < 0  # 負の値は下へ積む
    # 軸の種類: 積み上げ棒の X は常にカテゴリ
    open_tick_group(page, "x")
    assert "何個おきに" in page.inner_text("#xMajorStepHelp")


def test_hist_summary_density_and_hidden_x(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="hist", y=A)
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", B)
    wait_settled(page)
    s = axis0(page)
    assert len(s["bars"]["containers"]) == 2 and s["bars"]["horizontal"] == 0
    assert s["xlabel"] == "a [1]" and s["ylabel"] == "度数"
    assert is_hidden_by_id(page, "xColumn") and is_hidden_by_id(page, "series-s1-x") and is_hidden_by_id(page, "series-s2-errorbars")
    # 区間の数を指定すると、各容器の棒の数が区間の数になる
    page.fill("#histBins", "5")
    wait_settled(page)
    assert axis0(page)["bars"]["containers"] == [5, 5]
    previous = image_generation(page)
    page.check("#histDensity")
    wait_settled(page)
    assert axis0(page)["ylabel"] == "確率密度" and image_generation(page) != previous
    wait_code_generated(page)
    # X は数値の軸（日時の書式は出さない）
    assert is_hidden_by_id(page, "xDateFormatGroup")


def test_hist_bins_error_and_recovery(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="hist", y=A)
    page.fill("#histBins", "0")
    wait_error_status(page)
    assert "区間の数" in status_text(page) and code_is_stale(page)
    page.fill("#histBins", "")
    wait_settled(page)
    assert status_kind(page) != "error" and not code_is_stale(page)


def test_scatter_color_missing_column_error_and_recovery(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="scatterColor", x="__idx__1", y=B)
    wait_error_status(page)
    assert "色分けの列" in status_text(page) and "系列1" in status_text(page)
    assert code_is_stale(page)
    assert page.input_value("#series-s1-color-column") == ""
    options = page.eval_on_selector_all("#series-s1-color-column option", "els => els.map(e => e.textContent.trim())")
    assert options[0] == "（選択してください）" and len(options) == 7  # 空の選択肢 + 6 列
    page.select_option("#series-s1-color-column", C)
    wait_settled(page)
    assert status_kind(page) != "error" and not code_is_stale(page)
    cb = axis0(page)["colorbar"]
    assert cb["label"] == "c [3]"
    assert cb["cmap"] == "viridis" and cb["vmin"] == pytest.approx(-3.0) and cb["vmax"] == pytest.approx(13.5)
    # カラーマップとラベル
    page.select_option("#colorMap", "coolwarm")
    page.fill("#colorbarLabel", "電流 (A)")
    wait_settled(page)
    cb = axis0(page)["colorbar"]
    assert cb["cmap"] == "coolwarm" and cb["label"] == "電流 (A)"
    # 第2Y軸は使えない
    assert is_hidden_by_id(page, "series-s1-use-y2")


def test_color_column_reset_when_source_changes(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="scatterColor", x="__idx__1", y=B)
    page.select_option("#series-s1-color-column", C)
    wait_settled(page)
    add_files(page, [fixtures_dir / "band.csv"])
    wait_settled(page)
    page.select_option("#series-s1-source", "d2")
    wait_settled(page)
    assert series_state(page, "s1")["colorColumn"] == ""
    assert page.input_value("#series-s1-color-column") == ""


def test_hidden_invalid_value_does_not_block_rendering(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, y=B)
    # 隠れている欄は操作できないので、値の入力と同じイベントを送る
    page.evaluate(
        "() => { const e = document.getElementById('histBins'); e.value = '0'; e.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    page.evaluate(
        "() => { const e = document.getElementById('colorMap'); e.value = 'gray'; e.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    wait_settled(page)
    assert status_kind(page) != "error"
    assert axis0(page)["lines"] >= 1
    assert plot_settings(page)["hist"]["bins"] == 0  # 値は残る


def test_edit_mode_does_not_redraw_on_type_change(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="step", y=B)
    wait_code_generated(page)
    enter_edit_mode(page)
    before = (image_generation(page), code_text(page))
    page.select_option("#plotType", "hist")
    page.fill("#histBins", "5")
    page.wait_for_timeout(1000)
    assert (image_generation(page), code_text(page)) == before
    assert "編集" in status_text(page)


def test_narrow_screen_has_no_horizontal_scroll(page, app_url, fixtures_dir, console_log):
    page.set_viewport_size({"width": 375, "height": 800})
    start(page, app_url, fixtures_dir, plot_type="scatterColor", x="__idx__1", y=B)
    page.select_option("#series-s1-color-column", C)
    for plot_type in ("hist", "step", "scatterColor"):
        set_plot_type(page, plot_type)
        overflow = page.evaluate(
            """() => {
              const wide = [...document.querySelectorAll('#stepGroup, #histGroup, #colorMapGroup, .series-item')]
                .filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.id || e.className);
              return {page: document.documentElement.scrollWidth - window.innerWidth, wide};
            }"""
        )
        assert overflow["page"] <= 0 and overflow["wide"] == [], plot_type
