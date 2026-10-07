"""体裁セクション（プリセット・カラーパレット・図サイズの単位）と、軸・目盛セクションの数式の案内（C6）。"""
import pytest

from helpers import (
    act_and_wait_render,
    code_text,
    load_fixture,
    natural_size,
    open_code_tab,
    palette_grid_colors,
    series_color,
    wait_app_ready,
    wait_code_generated,
    wait_settled,
)

pytestmark = pytest.mark.e2e

TAB10 = ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF"]


def assert_same_size(page):
    """図の物理サイズが変わっていない（800×600。cm / mm でも生成コードは割り算でインチに直すので、画素数は欠けない）。"""
    assert natural_size(page) == (800, 600)


def start(page, app_url, fixtures_dir, fixture="utf8.csv"):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)


def test_unit_switch_converts_values_and_keeps_figure_size(page, app_url, fixtures_dir):
    start(page, app_url, fixtures_dir)
    assert natural_size(page) == (800, 600)
    assert page.input_value("#figUnit") == "in"
    assert page.inner_text('label[for="figWidth"]') == "図幅(inch)"

    act_and_wait_render(page, lambda: page.select_option("#figUnit", "cm"))
    assert page.input_value("#figWidth") == "20.32" and page.input_value("#figHeight") == "15.24"
    assert page.inner_text('label[for="figWidth"]') == "図幅(cm)"
    assert page.inner_text('label[for="figHeight"]') == "図高さ(cm)"
    assert_same_size(page)

    act_and_wait_render(page, lambda: page.select_option("#figUnit", "mm"))
    assert page.input_value("#figWidth") == "203.2" and page.input_value("#figHeight") == "152.4"
    assert page.get_attribute("#figWidth", "step") == "1"
    assert_same_size(page)

    act_and_wait_render(page, lambda: page.select_option("#figUnit", "in"))
    assert page.input_value("#figWidth") == "8" and page.input_value("#figHeight") == "6"
    assert page.inner_text('label[for="figWidth"]') == "図幅(inch)"
    assert natural_size(page) == (800, 600)


def test_unit_switch_leaves_blank_field_alone(page, app_url, fixtures_dir):
    start(page, app_url, fixtures_dir)
    page.fill("#figHeight", "")
    page.select_option("#figUnit", "cm")
    assert page.input_value("#figWidth") == "20.32"
    assert page.input_value("#figHeight") == ""


def test_preset_applies_only_on_button(page, app_url, fixtures_dir):
    start(page, app_url, fixtures_dir)
    # 折れ線（点サイズは自動）
    page.select_option("#stylePreset", "paper1")
    page.wait_for_timeout(600)  # 選ぶだけでは何も変わらない
    assert page.input_value("#figWidth") == "8" and page.input_value("#fontSize") == "15"
    act_and_wait_render(page, lambda: page.click("#applyPresetBtn"))
    assert page.input_value("#figWidth") == "8.5" and page.input_value("#figHeight") == "6.4"
    assert page.input_value("#figUnit") == "cm" and page.input_value("#fontSize") == "8"
    assert page.input_value("#series-s1-line-width") == "1"
    assert page.input_value("#series-s1-marker-size") == "0"  # 自動のまま（折れ線に点は出ない）
    assert page.input_value("#stylePreset") == "paper1"
    w, h = natural_size(page)
    assert abs(w - 335) <= 1 and abs(h - 252) <= 1
    wait_code_generated(page)
    open_code_tab(page)
    code = code_text(page)
    assert "8.5 / CM_PER_INCH" in code and "FONT_SIZE = 8" in code
    page.click("#tabPlotBtn")

    # 適用後に追加した系列は、プリセットの線幅になる
    page.click("#addSeriesBtn")
    assert page.input_value("#series-s2-line-width") == "1"

    # 選び直しただけでは変わらない
    page.select_option("#stylePreset", "slide")
    page.wait_for_timeout(600)
    assert page.input_value("#figWidth") == "8.5" and page.input_value("#fontSize") == "8"
    assert page.input_value("#series-s1-line-width") == "1"

    # 標準に戻す
    act_and_wait_render(page, lambda: (page.select_option("#stylePreset", "standard"), page.click("#applyPresetBtn")))
    assert page.input_value("#figWidth") == "8" and page.input_value("#figUnit") == "in"
    assert page.input_value("#series-s1-line-width") == "2"


def test_preset_sets_marker_size_on_scatter(page, app_url, fixtures_dir):
    start(page, app_url, fixtures_dir)
    page.select_option("#plotType", "scatter")
    wait_settled(page)
    assert page.input_value("#series-s1-marker-size") == "24"
    page.select_option("#stylePreset", "paper1")
    act_and_wait_render(page, lambda: page.click("#applyPresetBtn"))
    assert page.input_value("#series-s1-marker-size") == "9"
    page.click("#addSeriesBtn")
    assert page.input_value("#series-s2-marker-size") == "9"
    assert page.input_value("#series-s2-line-width") == "1"
    # 標準に戻すと点サイズは自動（散布図の既定 24）に戻る
    page.select_option("#stylePreset", "standard")
    act_and_wait_render(page, lambda: page.click("#applyPresetBtn"))
    assert page.input_value("#series-s1-marker-size") == "24"


def test_palette_recolors_all_series_and_picker(page, app_url, fixtures_dir):
    start(page, app_url, fixtures_dir)
    page.click("#series-s1-color-trigger")
    page.evaluate(
        """() => { const i = document.querySelector('#seriesList .series-color-custom');
          i.value = '#123456'; i.dispatchEvent(new Event('input', {bubbles: true})); }"""
    )
    assert series_color(page, "s1") == "#123456"
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__2")
    wait_settled(page)
    assert series_color(page, "s2") == "#FF4B00"

    act_and_wait_render(page, lambda: page.select_option("#colorPalette", "tab10"))
    assert series_color(page, "s1") == "#1F77B4" and series_color(page, "s2") == "#FF7F0E"
    assert palette_grid_colors(page, "s1") == TAB10

    page.click("#addSeriesBtn")
    assert series_color(page, "s3") == "#2CA02C"

    act_and_wait_render(page, lambda: page.select_option("#colorPalette", "gray"))
    assert [series_color(page, s) for s in ("s1", "s2", "s3")] == ["#000000", "#404040", "#707070"]
    assert palette_grid_colors(page, "s1") == ["#000000", "#404040", "#707070", "#909090", "#B0B0B0"]
    # 生成コードにも反映される
    wait_code_generated(page)
    open_code_tab(page)
    assert "#404040" in code_text(page).upper()
