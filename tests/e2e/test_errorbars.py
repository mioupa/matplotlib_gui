"""エラーバー（Phase 5a, G1）: 系列カードの入力欄、図の要約、コードタブの追従、複数ファイル、警告とエラー。"""
import pytest

from helpers import (
    add_files,
    add_series_with_source,
    code_is_stale,
    code_value,
    error_bar_count,
    eb_id,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    series_errorbars,
    set_errorbars,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

# errorbars.csv の列: 0 x, 1 y, 2 y2, 3 sd, 4 sd_low, 5 sd_high, 6 xsd
SD, LOW, HIGH, XSD = "__idx__3", "__idx__4", "__idx__5", "__idx__6"


def start(page, app_url, fixtures_dir, fixture="errorbars.csv", plot_type=None, x="__idx__0", y="__idx__1"):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    if plot_type:
        page.select_option("#plotType", plot_type)
    if x is not None and plot_type != "bar":
        page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", y)
    wait_settled(page)


def settle_code(page):
    wait_settled(page)
    wait_code_generated(page)


def test_card_is_closed_by_default_and_controls_follow_mode(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert page.evaluate("document.getElementById('series-s1-errorbars').open") is False
    assert page.inner_text("#series-s1-errorbars > summary") == "エラーバー"
    page.evaluate("document.getElementById('series-s1-errorbars').open = true")
    for name in ("symmetric", "value", "column"):
        assert is_hidden_by_id(page, eb_id("s1", "y", name)[1:]), name
    assert is_hidden_by_id(page, "series-s1-err-capsize")
    page.select_option(eb_id("s1", "y", "mode"), "fixed")
    assert not is_hidden_by_id(page, eb_id("s1", "y", "value")[1:]) and is_hidden_by_id(page, eb_id("s1", "y", "column")[1:])
    assert not is_hidden_by_id(page, "series-s1-err-capsize")
    assert page.inner_text('label[for="series-s1-yerr-value"]') == "値"
    assert is_hidden_by_id(page, eb_id("s1", "y", "value-minus")[1:])
    page.set_checked(eb_id("s1", "y", "symmetric"), False)  # 欄の表示切替はカードを作り直さない（フォーカスを保つ）
    assert page.inner_text('label[for="series-s1-yerr-value"]') == "上（+）"
    assert not is_hidden_by_id(page, eb_id("s1", "y", "value-minus")[1:])
    page.select_option(eb_id("s1", "y", "mode"), "column")
    assert not is_hidden_by_id(page, eb_id("s1", "y", "column")[1:]) and not is_hidden_by_id(page, eb_id("s1", "y", "column-minus")[1:])
    assert page.eval_on_selector(eb_id("s1", "y", "column"), "e => [...e.options].map(o => o.textContent)[0]") == "（列を選択）"
    page.select_option(eb_id("s1", "x", "mode"), "fixed")
    page.set_checked(eb_id("s1", "x", "symmetric"), False)
    assert page.inner_text('label[for="series-s1-xerr-value"]') == "右（+）"
    assert page.inner_text('label[for="series-s1-xerr-value-minus"]') == "左（−）"
    page.select_option(eb_id("s1", "y", "mode"), "none")
    assert is_hidden_by_id(page, eb_id("s1", "y", "symmetric")[1:])
    assert not is_hidden_by_id(page, "series-s1-err-capsize")  # X が使われている
    wait_settled(page)


def test_y_column_symmetric_line(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert error_bar_count(page) == 0
    set_errorbars(page, "s1", "y", mode="column", column=SD)
    settle_code(page)
    assert error_bar_count(page) > 0
    assert series_errorbars(page, "s1")["y"]["column"] == SD
    code = code_value(page)
    assert "draw_error_bars(" in code and "Y の誤差: sd [3]" in code
    assert status_kind(page) == "warning"  # 数値にできない値・負の値
    assert len(image_summary(page)[0]["legend"]) == 1


def test_y_columns_asymmetric(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_errorbars(page, "s1", "y", mode="column", symmetric=False, column=LOW, column_minus=HIGH)
    settle_code(page)
    assert error_bar_count(page) > 0
    code = code_value(page)
    assert "Y の誤差（上）: sd_low [4]" in code and "Y の誤差（下）: sd_high [5]" in code
    assert page.inner_text('label[for="series-s1-yerr-column"]') == "上（+）"
    assert page.inner_text('label[for="series-s1-yerr-column-minus"]') == "下（−）"


def test_fixed_values_symmetric_and_asymmetric(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_errorbars(page, "s1", "y", mode="fixed", value="0.5")
    settle_code(page)
    assert error_bar_count(page) > 0
    assert "draw_error_bars(" in code_value(page) and "y[ok] - 0.5" in code_value(page)
    set_errorbars(page, "s1", "y", symmetric=False, value="0.7", value_minus="0.2")
    settle_code(page)
    wait_code_contains(page, "y[ok] - 0.2")
    assert "y[ok] + 0.7" in code_value(page)
    ylim = image_summary(page)[0]["ylim"]
    assert ylim[1] > 0
    state = series_errorbars(page, "s1")["y"]
    assert state["value"] == 0.7 and state["valueMinus"] == 0.2 and state["symmetric"] is False


def test_scatter_and_x_direction(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, plot_type="scatter")
    set_errorbars(page, "s1", "y", mode="column", column=SD)
    set_errorbars(page, "s1", "x", mode="column", column=XSD)
    settle_code(page)
    summary = image_summary(page)[0]
    assert summary["errorbars"] >= 2 and summary["collections"] == 1
    code = code_value(page)
    assert 'direction="y"' in code and 'direction="x"' in code and "zorder=1" in code
    assert page.inner_text('label[for="series-s1-xerr-column"]') == "列"


def test_x_block_hidden_for_bar_and_bar_errors(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="categories.csv", x=None)
    page.evaluate("document.getElementById('series-s1-errorbars').open = true")
    assert page.is_visible(eb_id("s1", "x", "mode"))  # 折れ線では X 方向も指定できる
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)
    assert not page.is_visible(eb_id("s1", "x", "mode")) and page.is_visible(eb_id("s1", "y", "mode"))
    set_errorbars(page, "s1", "y", mode="fixed", value="2")
    settle_code(page)
    assert "yerr=2.0" in code_value(page)
    assert error_bar_count(page) >= 1
    page.select_option("#plotType", "line")  # 種類を戻すと X のブロックが出る
    assert page.is_visible(eb_id("s1", "x", "mode"))
    wait_settled(page)


def test_multi_series_bar_errors(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="categories.csv", x=None)
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    wait_settled(page)
    set_errorbars(page, "s1", "y", mode="fixed", value="1.5")
    set_errorbars(page, "s2", "y", mode="fixed", symmetric=False, value="3", value_minus="1")
    settle_code(page)
    code = code_value(page)
    assert code.count("yerr=") >= 2
    assert error_bar_count(page) >= 2
    assert image_summary(page)[0]["patches"] == 12


def test_datetime_x_with_y_errors(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="datetime.csv", y="__idx__3")  # 日時の列 + 温度
    set_errorbars(page, "s1", "y", mode="column", column="__idx__4")  # 湿度を誤差の大きさとして使う
    settle_code(page)
    assert error_bar_count(page) > 0 and "Date" in image_summary(page)[0]["xconverter"]
    # X 方向は日時の X では使えない
    set_errorbars(page, "s1", "x", mode="fixed", value="1")
    wait_error_status(page)
    assert "X" in status_text(page) and "日時" in status_text(page)
    assert code_is_stale(page)
    set_errorbars(page, "s1", "x", mode="none")
    settle_code(page)
    assert status_kind(page) != "error" and not code_is_stale(page)


def test_two_files_error_columns_follow_the_series_source(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")  # 時間 / 電圧 / 電流（3列）
    wait_settled(page)
    add_files(page, [fixtures_dir / "errorbars.csv"])
    page.select_option("#series-s1-y", "__idx__1")
    add_series_with_source(page, "d2", "__idx__1")
    page.evaluate("document.getElementById('series-s2-errorbars').open = true")
    options = page.eval_on_selector("#series-s2-yerr-column", "e => [...e.options].map(o => o.value)")
    assert "__idx__6" in options and len(options) == 8  # （列を選択）+ 7 列
    page.evaluate("document.getElementById('series-s1-errorbars').open = true")
    own = page.eval_on_selector("#series-s1-yerr-column", "e => [...e.options].map(o => o.value)")
    assert len(own) == 4  # （列を選択）+ 3 列
    set_errorbars(page, "s2", "y", mode="column", column=SD)
    settle_code(page)
    assert error_bar_count(page) > 0
    # データ元を替えると、誤差の列は空に戻り（方式は残る）、選び直すよう案内される
    page.select_option("#series-s2-source", "d1")
    wait_error_status(page)
    assert "Y誤差の列" in status_text(page) and "系列2" in status_text(page)
    state = series_errorbars(page, "s2")["y"]
    assert state["mode"] == "column" and state["column"] == ""
    assert code_is_stale(page)
    page.select_option("#series-s2-source", "d2")
    page.select_option("#series-s2-y", "__idx__1")
    set_errorbars(page, "s2", "y", column=SD)
    settle_code(page)
    assert status_kind(page) != "error" and error_bar_count(page) > 0 and not code_is_stale(page)


def test_warnings_for_non_numeric_and_negative_values(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_errorbars(page, "s1", "y", mode="column", column=SD)
    settle_code(page)
    text = status_text(page)
    assert status_kind(page) == "warning"
    assert "bad" in text  # 数値にできない値
    assert "負" in text


def test_column_mode_without_a_column_is_an_error_then_recovers(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_errorbars(page, "s1", "y", mode="column")
    wait_error_status(page)
    assert "Y誤差の列" in status_text(page) and "選んでください" in status_text(page)
    assert code_is_stale(page)
    set_errorbars(page, "s1", "y", column=SD)
    settle_code(page)
    assert status_kind(page) != "error" and not code_is_stale(page) and error_bar_count(page) > 0
    set_errorbars(page, "s1", "y", mode="none")
    settle_code(page)
    assert error_bar_count(page) == 0 and "draw_error_bars" not in code_value(page)


def test_card_open_state_survives_adding_a_series(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    page.click("#series-s1-errorbars > summary")
    assert page.evaluate("document.getElementById('series-s1-errorbars').open") is True
    page.click("#addSeriesBtn")
    wait_settled(page)
    assert page.evaluate("document.getElementById('series-s1-errorbars').open") is True
    assert page.evaluate("document.getElementById('series-s2-errorbars').open") is False
    page.click("#series-s1-errorbars > summary")  # 閉じた状態も保つ
    page.click("#addSeriesBtn")
    wait_settled(page)
    assert page.evaluate("document.getElementById('series-s1-errorbars').open") is False
    # 使っている系列は、作り直したときに開いている
    set_errorbars(page, "s2", "y", mode="fixed", value="1")
    wait_settled(page)
    page.evaluate("document.getElementById('series-s2-errorbars').open = false")
    page.click("#series-s3-remove")
    wait_settled(page)
    assert page.evaluate("document.getElementById('series-s2-errorbars').open") is False  # 閉じた開閉は保つ


def test_legend_is_unchanged_by_error_bars(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    before = image_summary(page)[0]["legend"]
    set_errorbars(page, "s1", "y", mode="fixed", value="1")
    settle_code(page)
    after = image_summary(page)[0]
    assert after["legend"] == before and after["errorbars"] > 0
