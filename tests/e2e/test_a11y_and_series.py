"""B6（アクセシビリティ属性）と B7（系列の既定色・点サイズ）。"""
import pytest

from helpers import wait_app_ready

pytestmark = pytest.mark.e2e


def test_tabs_and_labels_accessibility(page, app_url, console_log):
    page.goto(app_url)
    assert page.get_attribute(".tabs", "role") == "tablist"
    tabs = [("tabPlotBtn", "plotPanel"), ("tabDataBtn", "dataPanel"), ("tabCodeBtn", "codePanel")]
    for btn, panel in tabs:
        assert page.get_attribute(f"#{btn}", "role") == "tab"
        assert page.get_attribute(f"#{btn}", "aria-controls") == panel
        assert page.get_attribute(f"#{panel}", "role") == "tabpanel"
        assert page.get_attribute(f"#{panel}", "aria-labelledby") == btn
    assert [page.get_attribute(f"#{b}", "aria-selected") for b, _ in tabs] == ["true", "false", "false"]
    page.click("#tabDataBtn")
    assert [page.get_attribute(f"#{b}", "aria-selected") for b, _ in tabs] == ["false", "true", "false"]
    assert not page.is_visible("#plotPanel") and page.is_visible("#dataPanel")
    page.focus("#tabDataBtn")
    page.keyboard.press("ArrowRight")
    assert page.get_attribute("#tabCodeBtn", "aria-selected") == "true"
    assert page.evaluate("document.activeElement.id") == "tabCodeBtn"

    assert page.get_attribute("#status", "aria-live") == "polite"

    page.click("#addSeriesBtn")  # 系列が2つの状態でも全入力欄にラベルがある
    unlabeled = page.evaluate(
        """() => [...document.querySelectorAll('input, select, textarea')]
          .filter((el) => !(el.labels && el.labels.length) && !el.getAttribute('aria-label'))
          .map((el) => el.id || el.className)"""
    )
    assert unlabeled == []
    ids = page.evaluate("[...document.querySelectorAll('[id]')].map(e => e.id)")
    assert len(ids) == len(set(ids))  # id の重複なし（系列カードは系列 id で一意）
    assert page.get_attribute("label[for='series-s2-x']", "for") == "series-s2-x"


def test_new_series_default_color_is_first_unused(page, app_url, console_log):
    page.goto(app_url)
    colors = lambda: page.eval_on_selector_all("#seriesList .series-color-value", "els => els.map(e => e.textContent)")  # noqa: E731
    assert colors() == ["#FF4B00"]
    page.click("#series-s1-color-trigger")
    page.click(".series-color-chip[data-color='#005AFF']")
    page.click("#addSeriesBtn")
    assert colors() == ["#005AFF", "#FF4B00"]  # 空いた先頭色
    page.click("#addSeriesBtn")
    assert colors() == ["#005AFF", "#FF4B00", "#03AF7A"]
    page.click("#series-s2-remove")
    page.click("#addSeriesBtn")
    assert colors()[-1] == "#FF4B00"


def test_marker_size_auto_follows_plot_type_until_user_edits(page, app_url, console_log):
    page.goto(app_url)
    value = lambda: page.eval_on_selector("#series-s1-marker-size", "e => e.value")  # noqa: E731
    assert value() == "0"
    page.select_option("#plotType", "scatter")
    assert value() == "24"
    page.select_option("#plotType", "line")
    assert value() == "0"  # 自動値は種別に追従する（24 のまま残らない）

    page.fill("#series-s1-marker-size", "24")  # ユーザー入力は line でも 24 のまま保持される
    page.select_option("#plotType", "scatter")
    assert value() == "24"
    page.select_option("#plotType", "line")
    assert value() == "24"
    page.fill("#series-s1-marker-size", "10")
    page.select_option("#plotType", "scatter")
    page.select_option("#plotType", "line")
    assert value() == "10"
