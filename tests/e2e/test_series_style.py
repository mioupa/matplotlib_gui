"""系列のスタイル（Phase 5b, G3）: 点の形・不透明度・塗りつぶし帯・並べ替え・複製。"""
import pytest

from helpers import (
    add_files,
    code_value,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    series_ids,
    series_state,
    set_fill,
    state_list,
    status_kind,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

# band.csv の列: 0 x, 1 mean, 2 lo, 3 hi, 4 day, 5 other
X, MEAN, LO, HI, DAY, OTHER = (f"__idx__{i}" for i in range(6))


def start(page, app_url, fixtures_dir, fixture="band.csv", plot_type=None):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    if plot_type:
        page.select_option("#plotType", plot_type)
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", MEAN)
    wait_settled(page)


def test_marker_alpha_and_band(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert image_summary(page)[0]["bands"] == 0 and image_summary(page)[0]["markers"] == ["None"]
    assert page.evaluate("document.getElementById('series-s1-fill').open") is False  # 既定は閉じている
    assert page.inner_text("#series-s1-fill > summary") == "塗りつぶし帯"
    assert page.eval_on_selector("#series-s1-alpha", "e => e.labels[0].textContent") == "不透明度"
    # 点の形: 形を選ぶと点が描かれ、「なし」では点サイズの欄が使えない
    page.select_option("#series-s1-marker", "s")
    wait_settled(page)
    assert image_summary(page)[0]["markers"] == ["s"]
    assert "marker=" in code_value(page)
    assert not page.is_disabled("#series-s1-marker-size")
    page.select_option("#series-s1-marker", "none")
    wait_settled(page)
    assert page.is_disabled("#series-s1-marker-size") and image_summary(page)[0]["markers"] == ["None"]
    page.select_option("#series-s1-marker", "auto")
    # 不透明度
    page.fill("#series-s1-alpha", "0.5")
    wait_settled(page)
    assert image_summary(page)[0]["alphas"] == [0.5] and "alpha=0.5" in code_value(page)
    # 塗りつぶし帯: 下端だけではエラー、両方で帯。数値にできない値は警告
    set_fill(page, "s1", lower=LO)
    wait_error_status(page)
    assert "塗りつぶし帯" in status_text(page)
    set_fill(page, "s1", upper=HI)
    wait_settled(page)
    wait_code_generated(page)
    assert status_kind(page) == "warning" and any("下端" in w or "塗りつぶし" in w for w in status_warnings(page))
    assert image_summary(page)[0]["bands"] == 1 and "fill_between(" in code_value(page)
    assert page.evaluate("document.getElementById('series-s1-fill').open") is True
    # 棒グラフでは点の形と帯を隠す（不透明度は残る）。値は残り、帯は描かれない
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", X)
    wait_settled(page)
    assert is_hidden_by_id(page, "series-s1-marker") and is_hidden_by_id(page, "series-s1-fill-lower")
    assert not is_hidden_by_id(page, "series-s1-alpha")
    assert image_summary(page)[0]["bands"] == 0
    page.select_option("#plotType", "line")
    wait_settled(page)
    assert image_summary(page)[0]["bands"] == 1
    # scatter で「なし」は点が見えないのでエラー
    page.select_option("#plotType", "scatter")
    page.select_option("#series-s1-marker", "none")
    wait_error_status(page)
    assert "点の形" in status_text(page)
    page.select_option("#series-s1-marker", "auto")
    wait_settled(page)
    assert status_kind(page) != "error"


def test_band_with_datetime_x(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="scatter")
    page.select_option("#series-s1-x", DAY)
    set_fill(page, "s1", lower=LO, upper=HI, alpha=0.4)
    wait_settled(page)
    assert image_summary(page)[0]["bands"] == 1 and "alpha=0.4" in code_value(page)


def test_source_change_clears_band(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_fill(page, "s1", lower=LO, upper=HI)
    wait_settled(page)
    assert image_summary(page)[0]["bands"] == 1
    add_files(page, [fixtures_dir / "errorbars.csv"])
    page.select_option("#series-s1-source", "d2")
    wait_settled(page)
    state = series_state(page, "s1")
    assert state["fill"]["lower"] == "" and state["fill"]["upper"] == ""
    assert page.input_value("#series-s1-fill-lower") == ""
    assert any("塗りつぶし帯" in w for w in status_warnings(page))


def test_reorder_and_duplicate(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    page.fill("#series-s1-legend-name", "平均")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", X)
    page.select_option("#series-s2-y", OTHER)
    page.fill("#series-s2-legend-name", "別")
    wait_settled(page)
    assert series_ids(page) == ["s1", "s2"] and image_summary(page)[0]["legend"] == ["平均", "別"]
    # 端のボタンは無効、aria-label がある
    assert page.is_disabled("#series-s1-up") and page.is_disabled("#series-s2-down")
    assert page.get_attribute("#series-s1-down", "aria-label") == "系列 1 を下へ"
    assert page.get_attribute("#series-s2-duplicate", "aria-label") == "系列 2 を複製"
    page.click("#series-s1-down")
    wait_settled(page)
    assert series_ids(page) == ["s2", "s1"] and image_summary(page)[0]["legend"] == ["別", "平均"]
    assert page.is_disabled("#series-s2-up") and not page.is_disabled("#series-s2-down")
    # 複製: 元の系列の直後。色は別、設定は同じ、id は新しい
    page.fill("#series-s1-alpha", "0.6")
    page.select_option("#series-s1-marker", "^")
    wait_settled(page)
    page.click("#series-s1-duplicate")
    wait_settled(page)
    ids = series_ids(page)
    assert ids[:2] == ["s2", "s1"] and ids[2] not in ("s1", "s2") and len(ids) == 3 and ids[2] == "s3"
    copy, src = series_state(page, "s3"), series_state(page, "s1")
    assert copy["color"] != src["color"] and copy["marker"] == "^" and copy["alpha"] == 0.6 and copy["y"] == src["y"]
    assert image_summary(page)[0]["legend"] == ["別", "平均", "平均"]
    assert state_list(page, "fits") == []
