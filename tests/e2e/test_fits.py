"""近似曲線（Phase 5b, G5）: 凡例・図の中の式、棒グラフで隠れる、日時の X のエラー、系列の削除。"""
import pytest

from helpers import (
    add_fit,
    code_value,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    state_list,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

X, MEAN, DAY, OTHER = "__idx__0", "__idx__1", "__idx__4", "__idx__5"


def start(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", MEAN)
    page.fill("#series-s1-legend-name", "温度")
    wait_settled(page)


def test_linear_legend_poly_text_and_series_select(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert "対数軸" in page.inner_text("#sectionAnalysis")  # 近似は元の値で行う、という補足
    f = add_fit(page)
    assert page.eval_on_selector(f"#fit-{f}-series", "e => e.selectedOptions[0].textContent") == "系列1（温度）"
    assert is_hidden_by_id(page, f"fit-{f}-degree")
    wait_settled(page)
    s = image_summary(page)[0]
    assert s["fitlines"] == 1 and s["fittexts"] == 0
    label = [t for t in s["legend"] if t.startswith("温度の近似")]
    assert label and "y = " in label[0] and "R" in label[0]
    # 多項式で図の中に出す: 次数の欄が出る。式は凡例ではなく図の中
    page.select_option(f"#fit-{f}-model", "poly")
    assert not is_hidden_by_id(page, f"fit-{f}-degree")
    page.fill(f"#fit-{f}-degree", "3")
    page.select_option(f"#fit-{f}-show", "text")
    wait_settled(page)
    s = image_summary(page)[0]
    assert s["fitlines"] == 1 and s["fittexts"] == 1 and not [t for t in s["legend"] if "近似" in t]
    assert "poly_text(" in code_value(page)
    # 線の色: 「系列の色」のときは色の選択が隠れ、「色を選ぶ」で出る
    assert is_hidden_by_id(page, f"fit-{f}-color-picker-trigger")
    page.select_option(f"#fit-{f}-color", "custom")
    assert not is_hidden_by_id(page, f"fit-{f}-color-picker-trigger")
    assert state_list(page, "fits")[0]["color"] != ""
    # 系列の名前を変えると選択肢に追従する。系列を足すと選べる
    page.fill("#series-s1-legend-name", "気温")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", X)
    page.select_option("#series-s2-y", OTHER)
    wait_settled(page)
    texts = page.eval_on_selector(f"#fit-{f}-series", "e => [...e.options].map(o => o.textContent)")
    assert texts[0] == "系列1（気温）" and texts[1].startswith("系列2")
    page.select_option(f"#fit-{f}-series", "s2")
    wait_settled(page)
    assert state_list(page, "fits")[0]["series"] == "s2"
    # 棒グラフでは一覧と追加ボタンを隠し、案内を出す。値は残る
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", X)
    wait_settled(page)
    assert is_hidden_by_id(page, "fitList") and is_hidden_by_id(page, "addFitBtn")
    assert page.inner_text("#fitBarNote") == "棒グラフでは近似曲線は使えません。"
    assert image_summary(page)[0]["fitlines"] == 0
    page.select_option("#plotType", "line")
    wait_settled(page)
    assert not is_hidden_by_id(page, "fitList") and is_hidden_by_id(page, "fitBarNote")
    # 系列を削除すると、その近似曲線も消え、知らせる
    page.click("#series-s2-remove")
    wait_settled(page)
    assert state_list(page, "fits") == [] and page.locator("#fitList .fit-item").count() == 0
    assert any("近似曲線" in w for w in status_warnings(page))
    assert image_summary(page)[0]["fitlines"] == 0


def test_datetime_x_is_an_error_and_recovers(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_fit(page)
    wait_settled(page)
    assert image_summary(page)[0]["fitlines"] == 1
    page.select_option("#series-s1-x", DAY)
    wait_error_status(page)
    assert "近似曲線" in status_text(page)
    page.select_option("#series-s1-x", X)
    wait_settled(page)
    assert image_summary(page)[0]["fitlines"] == 1
