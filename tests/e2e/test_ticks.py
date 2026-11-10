"""目盛・軸の反転・枠線・日時の範囲（Phase 5a, G2）。入力欄の表示・無効の切り替え、図の要約、コードタブの追従。"""
import datetime as dt
import re

import pytest

from helpers import (
    act_and_wait_render,
    code_is_stale,
    code_value,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    open_tick_group,
    set_axis_option,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def start(page, app_url, fixtures_dir, fixture="growth.csv", x="__idx__0", y="__idx__1", open_groups=("x", "y")):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    if x is not None:
        page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", y)
    wait_settled(page)
    for axis in open_groups:
        open_tick_group(page, axis)


def axis0(page):
    return image_summary(page)[0]


def floats(labels):
    return [float(t.replace("−", "-")) for t in labels if t]


def test_default_state_hides_secondary_group_and_numeric_axis_controls(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert is_hidden_by_id(page, "y2TickGroup")
    assert is_hidden_by_id(page, "xMajorStepUnitWrap") and is_hidden_by_id(page, "xDateRangeGroup")
    assert not is_hidden_by_id(page, "xRangeGroup")
    assert not is_hidden_by_id(page, "xMinorGroup") and not is_hidden_by_id(page, "xTickFormatGroup")
    assert is_hidden_by_id(page, "xMinorDivisionsWrap") and is_hidden_by_id(page, "yTickDecimalsWrap")
    assert page.inner_text("#xMajorStepHelp") == "空欄は自動です。"
    assert page.is_enabled("#spineRight") and is_hidden_by_id(page, "spineRightHelp")
    assert page.get_attribute("#xTickGroup", "class") == "tick-details"


def test_y_major_step_changes_ticks_and_code(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert axis0(page)["ymajor"] == "AutoLocator"
    set_axis_option(page, "#yMajorStep", "200")
    s = axis0(page)
    assert s["ymajor"] == "MultipleLocator"
    assert all(v % 200 == 0 for v in floats(s["yticklabels"]))
    wait_code_generated(page)
    wait_code_contains(page, "MultipleLocator(200.0)")
    assert "import matplotlib.ticker as ticker" in code_value(page)
    set_axis_option(page, "#yMajorStep", "")
    assert axis0(page)["ymajor"] == "AutoLocator"
    wait_code_generated(page)
    assert "MultipleLocator" not in code_value(page)


def test_minor_ticks_on_off_auto_and_divisions(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert axis0(page)["yminor"] == "NullLocator"  # 自動: 副目盛線を出さなければ副目盛なし
    set_axis_option(page, "#yMinorTicks", "on")
    assert not is_hidden_by_id(page, "yMinorDivisionsWrap")
    assert axis0(page)["yminor"] == "AutoMinorLocator"
    set_axis_option(page, "#yMinorDivisions", "4")
    wait_code_generated(page)
    wait_code_contains(page, "AutoMinorLocator(4)")
    # 副目盛線を表示しても、表示の設定が優先される
    set_axis_option(page, "#showMinorGrid", True)
    assert axis0(page)["yminor"] == "AutoMinorLocator"
    set_axis_option(page, "#yMinorTicks", "off")
    assert is_hidden_by_id(page, "yMinorDivisionsWrap")
    assert axis0(page)["yminor"] == "NullLocator"  # 「表示しない」では副目盛線も出ない
    set_axis_option(page, "#yMinorTicks", "auto")
    assert axis0(page)["yminor"] == "AutoMinorLocator"  # 自動 + 副目盛線 = 今までの動き
    set_axis_option(page, "#showMinorGrid", False)
    assert axis0(page)["yminor"] == "NullLocator"


def test_tick_formats(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_axis_option(page, "#yTickFormat", "fixed")
    assert not is_hidden_by_id(page, "yTickDecimalsWrap")
    set_axis_option(page, "#yTickDecimals", "2")
    s = axis0(page)
    assert s["yformatter"] == "FormatStrFormatter"
    assert all(re.fullmatch(r"-?\d+\.\d\d", t) for t in s["yticklabels"] if t)
    wait_code_generated(page)
    wait_code_contains(page, 'FormatStrFormatter("%.2f")')
    set_axis_option(page, "#yTickFormat", "sci")
    assert not is_hidden_by_id(page, "yTickDecimalsWrap")
    s = axis0(page)
    assert all("e" in t for t in s["yticklabels"] if t)
    set_axis_option(page, "#yTickFormat", "pow10")
    assert is_hidden_by_id(page, "yTickDecimalsWrap")
    s = axis0(page)
    assert s["yformatter"] == "ScalarFormatter" and s["yoffset"]  # 軸の端に ×10^n をまとめて書く
    wait_code_generated(page)
    wait_code_contains(page, "useMathText=True")
    set_axis_option(page, "#yTickFormat", "auto")
    assert axis0(page)["yformatter"] == "ScalarFormatter" and not axis0(page)["yoffset"]


def test_inverted_axes(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    s = axis0(page)
    assert not s["xinverted"] and not s["yinverted"]
    set_axis_option(page, "#xInverted", True)
    s = axis0(page)
    assert s["xinverted"] and s["xlim"][0] > s["xlim"][1] and not s["yinverted"]
    wait_code_generated(page)
    wait_code_contains(page, "invert_xaxis()")
    set_axis_option(page, "#yInverted", True)
    assert axis0(page)["yinverted"]
    wait_code_generated(page)
    wait_code_contains(page, "invert_yaxis()")
    set_axis_option(page, "#xInverted", False)
    set_axis_option(page, "#yInverted", False)
    wait_code_generated(page)
    assert "invert_" not in code_value(page)


def test_spines_and_secondary_axis(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert axis0(page)["spines"] == {"top": True, "right": True}
    set_axis_option(page, "#spineTop", False)
    assert axis0(page)["spines"] == {"top": False, "right": True}
    wait_code_generated(page)
    wait_code_contains(page, 'spines["top"].set_visible(False)')
    set_axis_option(page, "#spineRight", False)
    assert axis0(page)["spines"] == {"top": False, "right": False}
    wait_code_generated(page)
    wait_code_contains(page, 'spines["right"].set_visible(False)')
    # 第2Y軸を使うと、右の枠線（第2Y軸の線）は消せない
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__2")
    act_and_wait_render(page, lambda: page.check("#series-s2-use-y2"))
    assert page.is_disabled("#spineRight") and not is_hidden_by_id(page, "spineRightHelp")
    assert "消せません" in page.inner_text("#spineRightHelp")
    assert not is_hidden_by_id(page, "y2TickGroup")
    summary = image_summary(page)
    assert len(summary) == 2 and all(ax["spines"]["right"] is True for ax in summary)  # 設定の値は残るが、使わない
    assert all(ax["spines"]["top"] is False for ax in summary)
    act_and_wait_render(page, lambda: page.uncheck("#series-s2-use-y2"))
    assert page.is_enabled("#spineRight") and is_hidden_by_id(page, "spineRightHelp") and is_hidden_by_id(page, "y2TickGroup")
    assert image_summary(page)[0]["spines"]["right"] is False


def test_y2_tick_settings_apply_to_second_axis(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, open_groups=("x", "y"))
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__2")
    act_and_wait_render(page, lambda: page.check("#series-s2-use-y2"))
    open_tick_group(page, "y2")
    set_axis_option(page, "#y2MajorStep", "5")
    summary = image_summary(page)
    assert summary[1]["ymajor"] == "MultipleLocator" and summary[0]["ymajor"] == "AutoLocator"
    wait_code_generated(page)
    wait_code_contains(page, "ax2.yaxis.set_major_locator(ticker.MultipleLocator(5.0))")
    set_axis_option(page, "#y2Inverted", True)
    assert image_summary(page)[1]["yinverted"] is True


def test_log_scale_disables_the_step_and_does_not_use_it(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_axis_option(page, "#yMajorStep", "200")
    wait_code_generated(page)
    wait_code_contains(page, "MultipleLocator(200.0)")
    set_axis_option(page, "#yScale", "log")
    assert page.is_disabled("#yMajorStep")
    assert "対数軸では使えません" in page.inner_text("#yMajorStepHelp")
    assert page.input_value("#yMajorStep") == "200"  # 値は消さない
    assert axis0(page)["ymajor"] == "LogLocator"
    assert status_kind(page) != "error"
    wait_code_generated(page)
    assert "MultipleLocator" not in code_value(page)
    set_axis_option(page, "#yScale", "linear")
    assert page.is_enabled("#yMajorStep") and page.inner_text("#yMajorStepHelp") == "空欄は自動です。"
    assert axis0(page)["ymajor"] == "MultipleLocator"  # 戻すと効く
    # 対数軸のとき、隠れている分割数・間隔は使われない（不正な値でもエラーにならない）
    set_axis_option(page, "#yScale", "log")
    page.evaluate(
        "() => { const e = document.getElementById('yMajorStep'); e.value = '-5'; e.dispatchEvent(new Event('input', { bubbles: true })); }"
    )
    wait_settled(page)
    assert status_kind(page) != "error"


def test_x_log_scale_disables_x_step(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="utf8.csv", x="__idx__0", y="__idx__2")
    set_axis_option(page, "#xScale", "log")
    assert page.is_disabled("#xMajorStep") and "対数軸では使えません" in page.inner_text("#xMajorStepHelp")
    assert is_hidden_by_id(page, "xMinorDivisionsWrap")


def test_datetime_x_shows_unit_and_date_range_and_hides_numeric_controls(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="datetime.csv", x="__idx__0", y="__idx__3")
    assert not is_hidden_by_id(page, "xMajorStepUnitWrap") and not is_hidden_by_id(page, "xDateRangeGroup")
    assert is_hidden_by_id(page, "xRangeGroup") and is_hidden_by_id(page, "xTickFormatGroup")
    assert "整数で、単位の何個ごと" in page.inner_text("#xMajorStepHelp")
    assert page.inner_text("#xMajorStepUnit option[value=month]") == "月"
    # 月ごと
    set_axis_option(page, "#xMajorStepUnit", "month", wait=False)
    set_axis_option(page, "#xMajorStep", "1")
    s = axis0(page)
    assert s["xmajor"] == "MonthLocator"
    wait_code_generated(page)
    wait_code_contains(page, "mdates.MonthLocator(interval=1)")
    set_axis_option(page, "#xMajorStepUnit", "day")
    assert axis0(page)["xmajor"] == "DayLocator"
    wait_code_generated(page)
    wait_code_contains(page, "mdates.DayLocator(interval=1)")
    # 日時の範囲: xlim が日時の数値で指定した範囲になる
    page.fill("#xDateMin", "2026-01-02")
    set_axis_option(page, "#xDateMax", "2026-01-04 12:00")
    s = axis0(page)
    base = dt.date(1970, 1, 1)
    assert s["xlim"][0] == pytest.approx((dt.date(2026, 1, 2) - base).days)
    assert s["xlim"][1] == pytest.approx((dt.date(2026, 1, 4) - base).days + 0.5)
    wait_code_generated(page)
    wait_code_contains(page, 'ax.set_xlim(left=pd.Timestamp("2026-01-02"), right=pd.Timestamp("2026-01-04 12:00:00"))')
    # 日時の列でなくなると、日時の欄は隠れ、数値の欄が戻る（間隔は数値の軸の間隔になるので、空にしておく）
    page.fill("#xMajorStep", "")
    wait_settled(page)
    page.select_option("#series-s1-x", "__idx__2")
    wait_settled(page)
    assert is_hidden_by_id(page, "xDateRangeGroup") and not is_hidden_by_id(page, "xRangeGroup")
    assert is_hidden_by_id(page, "xMajorStepUnitWrap") and not is_hidden_by_id(page, "xTickFormatGroup")
    assert status_kind(page) != "error"
    assert axis0(page)["xlim"][0] > 900  # 通番（1001〜）。隠れた日時の範囲は使わない


def test_invalid_date_range_is_an_error_only_while_x_is_datetime(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="datetime.csv", x="__idx__0", y="__idx__3")
    page.fill("#xDateMin", "来月")
    wait_error_status(page)
    assert "X軸の範囲（日時）" in status_text(page) and "2026-01-31" in status_text(page)
    wait_code_generated_or_stale(page)
    # 日時でない X に替えると、隠れた不正な値は描画を止めない
    act_and_wait_render(page, lambda: page.select_option("#series-s1-x", "__idx__2"))
    assert status_kind(page) != "error" and not code_is_stale(page)
    assert page.input_value("#xDateMin") == "来月"  # 値は消さない
    # 日時の X に戻すと、再びエラー。直すと復帰する
    page.select_option("#series-s1-x", "__idx__0")
    wait_error_status(page)
    act_and_wait_render(page, lambda: page.fill("#xDateMin", "2026-01-02"))
    assert status_kind(page) != "error"
    page.fill("#xDateMax", "2026-01-01")  # 最小値 >= 最大値
    wait_error_status(page)
    assert "最小値 < 最大値" in status_text(page)


def wait_code_generated_or_stale(page):
    page.wait_for_function("document.getElementById('customPyCode').dataset.stale === 'true'")


def test_category_x_step_and_hidden_controls(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, fixture="datetime.csv", x="__idx__1", y="__idx__3")  # ID（A-001…）は文字列の列
    assert "何個おきに" in page.inner_text("#xMajorStepHelp")
    assert is_hidden_by_id(page, "xMinorGroup") and is_hidden_by_id(page, "xTickFormatGroup")
    assert is_hidden_by_id(page, "xMajorStepUnitWrap") and not is_hidden_by_id(page, "xRangeGroup")
    set_axis_option(page, "#xMajorStep", "10")
    assert axis0(page)["xmajor"] == "MultipleLocator"
    labels = [t for t in axis0(page)["xticklabels"] if t]
    assert 10 <= len(labels) <= 20 and labels[0] == "A-001"
    wait_code_generated(page)
    wait_code_contains(page, "MultipleLocator(10)")
    # 整数でない間隔はエラー
    page.fill("#xMajorStep", "2.5")
    wait_error_status(page)
    assert "X軸の主目盛の間隔" in status_text(page) and "整数" in status_text(page)
    act_and_wait_render(page, lambda: page.fill("#xMajorStep", "5"))
    assert status_kind(page) != "error"


def test_multi_series_bar_step(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "categories.csv")
    wait_settled(page)
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    wait_settled(page)
    open_tick_group(page, "x")
    assert "何個おきに" in page.inner_text("#xMajorStepHelp") and is_hidden_by_id(page, "xMinorGroup")
    assert len([t for t in axis0(page)["xticklabels"] if t]) == 6
    set_axis_option(page, "#xMajorStep", "2")
    labels = [t for t in axis0(page)["xticklabels"] if t]
    assert len(labels) == 3 and labels[0] == "品目A"
    wait_code_generated(page)
    wait_code_contains(page, "tick_step = 2")


def test_too_many_ticks_error_marks_code_stale_and_recovers(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert not code_is_stale(page)
    page.fill("#yMajorStep", "0.5")  # Y は 1〜1000 台。約 2,000 本になる
    wait_error_status(page)
    assert "主目盛の間隔" in status_text(page) and "小さすぎます" in status_text(page)
    wait_code_generated_or_stale(page)
    assert code_is_stale(page)
    act_and_wait_render(page, lambda: page.fill("#yMajorStep", "200"))
    assert status_kind(page) != "error" and not code_is_stale(page)
    wait_code_contains(page, "MultipleLocator(200.0)")


def test_hidden_decimals_and_divisions_do_not_block_drawing(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    # 書式が小数・指数でない、副目盛が「表示」でないとき、桁数・分割数は隠れていて使わない
    page.evaluate(
        """() => {
          for (const [id, v] of [['yTickDecimals', '99'], ['yMinorDivisions', '99']]) {
            const e = document.getElementById(id);
            e.value = v;
            e.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }"""
    )
    wait_settled(page)
    assert status_kind(page) != "error"
    set_axis_option(page, "#yTickFormat", "fixed", wait=False)
    wait_error_status(page)
    assert "小数の桁数" in status_text(page)
    act_and_wait_render(page, lambda: page.fill("#yTickDecimals", "2"))
    assert status_kind(page) != "error"
