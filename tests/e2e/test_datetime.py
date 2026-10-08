"""日時の列（D5）: 認識、日時の軸、表示書式、自動認識の切り替え、棒グラフ、Excel の日時セル、エラー。"""
import re

import pytest

from helpers import (
    change_load_option,
    code_text,
    image_summary,
    load_fixture,
    open_code_tab,
    plot_src,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_plot_changed,
    wait_settled,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def start(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    return page


def labels(page):
    return [t for t in image_summary(page)[0]["xticklabels"] if t]


def pick(page, x, y):
    page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", y)
    wait_settled(page)


def choose_format(page, value):
    before = plot_src(page)
    page.select_option("#xDateFormat", value)
    wait_plot_changed(page, before)
    wait_settled(page)


def test_datetime_csv_draws_a_date_axis_with_warning_and_tag(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    assert page.is_hidden("#xDateFormatGroup")  # X が行番号のあいだは出ない
    pick(page, "__idx__0", "__idx__3")
    assert status_kind(page) in ("ok", "warning")
    summary = image_summary(page)[0]
    assert "Date" in summary["xconverter"] and summary["lines"] == 1
    assert any(re.search(r"\d", t) for t in labels(page))
    assert "日時として読めない値が1件" in status_text(page) and "測定エラー" in status_text(page)
    assert page.is_visible("#xDateFormatGroup")
    assert page.locator("#dataArea th .col-kind-tag").count() == 1
    assert page.locator("#dataArea th .col-kind-tag").first.text_content() == "日時"
    open_code_tab(page)
    text = code_text(page)
    assert 'df.isetitem(0, pd.to_datetime(df.iloc[:, 0], format="%Y/%m/%d %H:%M", errors="coerce"))' in text
    assert "mdates.ConciseDateFormatter(date_locator)" in text and "set_xscale" not in text
    # ID（A-001）は文字列、通番は数値のまま
    options = page.inner_text("#series-s1-x")
    assert "ID [1]" in options and "日時 [0]" in options


def test_date_format_presets_and_custom(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__3")
    choose_format(page, "%m/%d")
    assert labels(page) and all(re.fullmatch(r"\d\d/\d\d", t) for t in labels(page))
    wait_code_generated(page)
    wait_code_contains(page, 'mdates.DateFormatter("%m/%d")')
    assert page.is_hidden("#xDateFormatCustom")
    before = plot_src(page)
    page.select_option("#xDateFormat", "custom")
    assert page.is_visible("#xDateFormatCustom")
    page.fill("#xDateFormatCustom", "%m月%d日 %H時")
    wait_plot_changed(page, before)
    wait_settled(page)
    assert all("月" in t and "時" in t for t in labels(page))
    wait_code_contains(page, 'mdates.DateFormatter("%m月%d日 %H時")')
    choose_format(page, "")  # 自動に戻す
    wait_code_contains(page, "ConciseDateFormatter")


def test_invalid_date_format_is_a_japanese_error(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__3")
    page.select_option("#xDateFormat", "custom")
    page.fill("#xDateFormatCustom", "年月日")  # % が無い
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "X軸の日時の書式" in status_text(page)


def test_x_range_with_datetime_is_an_error_and_recovers(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__3")
    page.fill("#xMin", "5")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "X軸の最小値・最大値は指定できません" in status_text(page)
    before = plot_src(page)
    page.fill("#xMin", "")
    wait_settled(page)
    assert status_kind(page) != "error"


def test_unchecking_parse_dates_makes_the_column_text(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__3")
    assert page.is_visible("#xDateFormatGroup") and page.is_checked("#parseDates")
    change_load_option(page, lambda: page.uncheck("#parseDates"))
    assert page.is_hidden("#xDateFormatGroup")
    assert page.locator("#dataArea th .col-kind-tag").count() == 0
    summary = image_summary(page)[0]
    assert "Date" not in (summary["xconverter"] or "")
    open_code_tab(page)
    assert "to_datetime" not in code_text(page)
    assert "set_xscale" not in code_text(page) and "MaxNLocator" in code_text(page)  # 文字列の X は目盛を間引く（150 種）
    change_load_option(page, lambda: page.check("#parseDates"))
    assert page.is_visible("#xDateFormatGroup")


def test_bar_chart_with_japanese_dates(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "dates_ja.csv")
    wait_settled(page)
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)
    assert page.is_visible("#xDateFormatGroup")
    assert labels(page)[0] == "2026-01-05" and len(labels(page)) == 8
    choose_format(page, "%m/%d")
    assert labels(page)[0] == "01/05"
    wait_code_contains(page, '.dt.strftime("%m/%d")')


def test_excel_datetime_cells_are_dates(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.xlsx")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__1")
    assert "Date" in image_summary(page)[0]["xconverter"]
    open_code_tab(page)
    assert "to_datetime" not in code_text(page) and "ConciseDateFormatter" in code_text(page)
    change_load_option(page, lambda: page.uncheck("#parseDates"))  # Excel の日時セルは、設定に関係なく日時
    assert "Date" in image_summary(page)[0]["xconverter"]


def test_mixed_datetime_and_number_x_is_an_error(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    pick(page, "__idx__0", "__idx__3")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__2")
    page.select_option("#series-s2-y", "__idx__4")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "同じ図に描くことはできません" in status_text(page)


def test_iso_with_timezone_fixture_warns_about_mixed_offsets(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "datetime_iso_tz.csv")
    wait_settled(page)
    pick(page, "__idx__1", "__idx__2")
    assert "UTC の時刻にそろえました" in status_text(page)
    assert "Date" in image_summary(page)[0]["xconverter"]
