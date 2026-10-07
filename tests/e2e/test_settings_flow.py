"""描画設定を順に変えて、そのたびにエラーなく再描画されること（設定オブジェクト → Python 経路の確認）。"""
import pytest

from helpers import (
    load_fixture,
    plot_src,
    status_kind,
    status_text,
    wait_app_ready,
    wait_plot_changed,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def _changed_ok(page, previous):
    new = wait_plot_changed(page, previous)
    wait_settled(page)
    assert status_kind(page) == "ok", status_text(page)
    assert status_text(page).startswith("描画に成功しました")
    return new


def test_changing_settings_rerenders_without_error(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    src = _changed_ok(page, "")
    assert "1系列" in status_text(page)

    steps = []

    # プロット種別: scatter
    page.select_option("#plotType", "scatter")
    steps.append("scatter")
    src = _changed_ok(page, src)
    assert page.eval_on_selector("#series-s1-marker-size", "e => e.value") == "24"  # 点サイズは自動値を表示する

    # 系列の色
    page.click("#series-s1-color-trigger")
    page.click(".series-color-chip[data-color='#005AFF']")
    steps.append("color")
    src = _changed_ok(page, src)
    assert page.eval_on_selector("#seriesList .series-color-value", "e => e.textContent") == "#005AFF"

    # 系列追加（既定色は未使用のパレット色）+ 第2軸
    page.click("#addSeriesBtn")
    assert page.eval_on_selector_all("#seriesList .series-item", "els => els.length") == 2
    assert page.eval_on_selector_all("#seriesList .series-color-value", "els => els.map(e => e.textContent)")[1] == "#FF4B00"
    src = _changed_ok(page, src)
    assert "2系列" in status_text(page)
    assert not page.is_visible("#y2LabelGroup")
    page.check("#seriesList .series-item:nth-child(2) .series-use-y2")
    steps.append("secondary axis")
    src = _changed_ok(page, src)
    assert page.is_visible("#y2LabelGroup") and page.is_visible("#y2AxisSettingsGroup")
    page.fill("#y2Label", "第2軸")
    src = _changed_ok(page, src)

    # 軸の範囲
    page.fill("#xMin", "1")
    page.fill("#xMax", "2")
    steps.append("axis range")
    src = _changed_ok(page, src)

    # 凡例位置
    page.select_option("#legendLocation", "upper left")
    steps.append("legend")
    src = _changed_ok(page, src)
    page.select_option("#legendLocation", "none")
    src = _changed_ok(page, src)

    # bar に切替（X列は共通）
    page.select_option("#plotType", "bar")
    assert page.is_visible("#globalXGroup")
    src = _changed_ok(page, src)

    # 不正な入力は日本語で項目名つきのエラーになり、直すと復帰する
    page.fill("#skipRows", "1.5")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    wait_settled(page)
    assert "「除外する先頭行数」" in status_text(page)
    assert plot_src(page) == src  # 前の画像は残る
    page.fill("#skipRows", "2")
    src = _changed_ok(page, src)
    assert "スキップ2行" in status_text(page)

    assert [e for e in console_log.events if e[2] == "pageerror"] == []
