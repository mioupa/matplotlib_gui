"""サブプロットのパネル（Phase 5e, G9）: 配置と欄の出し分け、パネルへの振り分け、タイトル・軸ラベル、配置を小さくしたときの付け替え、
軸の共有の無効化、種類の不一致のエラーと復帰、編集モード、狭い画面。"""
import pytest

from helpers import (
    add_annotation,
    code_text,
    enter_edit_mode,
    image_generation,
    image_summary,
    is_disabled,
    is_hidden_by_id,
    load_fixture,
    option_labels,
    panel_state,
    series_state,
    set_layout,
    set_series_panel,
    state_list,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

X, MEAN, LO, DAY, OTHER = "__idx__0", "__idx__1", "__idx__2", "__idx__4", "__idx__5"


def start(page, app_url, fixtures_dir, fixture="band.csv", plot_type=None):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    if plot_type:
        page.select_option("#plotType", plot_type)
    if fixture == "band.csv":
        page.select_option("#series-s1-x", X)
        page.select_option("#series-s1-y", MEAN)
    wait_settled(page)


def add_second_series(page, y=OTHER, x=X):
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", x)
    page.select_option("#series-s2-y", y)


def test_layout_fields_and_panel_selects_only_when_multi_panel(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_annotation(page, "hline", y="2")
    ann = state_list(page, "annotations")[0]["id"]
    hidden = ["layoutOptionsGroup", "series-s1-panel", f"annotation-{ann}-panel", "panelLabelsGroup", "titlePanelHelp"]
    assert all(is_hidden_by_id(page, i) for i in hidden)
    assert not is_hidden_by_id(page, "layoutRows") and not is_hidden_by_id(page, "layoutCols")
    set_layout(page, 1, 2)
    assert not any(is_hidden_by_id(page, i) for i in hidden)
    expected = {"0": "パネル1（1行目・1列目）", "1": "パネル2（1行目・2列目）"}
    assert option_labels(page, "series-s1-panel") == expected
    assert option_labels(page, f"annotation-{ann}-panel") == expected
    assert panel_state(page)["layout"]["cols"] == 2
    assert "図全体の上" in page.inner_text("#titlePanelHelp")
    set_layout(page, 2, 2)
    assert option_labels(page, "series-s1-panel")["3"] == "パネル4（2行目・2列目）"
    set_layout(page, 1, 1)
    assert all(is_hidden_by_id(page, i) for i in hidden)


def test_series_assigned_to_panels_in_summary(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_second_series(page)
    set_layout(page, 1, 2)
    assert series_state(page, "s2")["panel"] == 0  # 新しい系列は直前の系列と同じパネル
    set_series_panel(page, "s2", 1, wait=True)
    summary = image_summary(page)
    assert status_kind(page) != "error"
    assert [ax["panel"] for ax in summary] == [[0, 0], [0, 1]]
    assert [ax["lines"] for ax in summary] == [1, 1]
    assert all(ax["axison"] for ax in summary)
    assert summary[0]["suptitle"] == ""
    # 使わないパネル（2×2 の 3・4 番目）は軸を消す
    set_layout(page, 2, 2)
    summary = image_summary(page)
    assert [ax["axison"] for ax in summary] == [True, True, False, False]
    assert summary[2]["panel"] == [1, 0]


def test_panel_titles_and_axis_labels(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_second_series(page)
    page.check("#series-s2-use-y2")
    set_layout(page, 1, 2)
    set_series_panel(page, "s2", 1, wait=True)
    # 第2Y軸の欄は、第2軸の系列があるパネルだけ
    assert is_hidden_by_id(page, "panel-1-y2label") and not is_hidden_by_id(page, "panel-2-y2label")
    assert page.get_attribute("#panel-1-xlabel", "placeholder") == "自動"
    page.fill("#xLabel", "時間 (s)")
    assert page.get_attribute("#panel-1-xlabel", "placeholder") == "時間 (s)"
    page.evaluate("document.getElementById('panelLabelsGroup').open = true")
    page.fill("#panel-1-title", "パネルA")
    page.fill("#panel-2-ylabel", "右パネルの値")
    page.fill("#title", "図全体")
    wait_settled(page)
    summary = image_summary(page)
    assert summary[0]["title"] == "パネルA" and summary[0]["suptitle"] == "図全体"
    assert summary[1]["ylabel"] == "右パネルの値" and summary[0]["xlabel"] == "時間 (s)"
    assert panel_state(page)["panels"][1]["yLabel"] == "右パネルの値"


def test_shrinking_layout_moves_series_and_annotations(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_second_series(page)
    set_layout(page, 2, 2)
    set_series_panel(page, "s2", 3)
    ann = add_annotation(page, "hline", y="2")
    page.select_option(f"#annotation-{ann}-panel", "2")
    wait_settled(page)
    set_layout(page, 1, 2)
    assert series_state(page, "s2")["panel"] == 1
    assert state_list(page, "annotations")[0]["panel"] == 1
    text = status_text(page)
    assert "系列2: パネル4が無くなったため、パネル2に移しました。" in text
    assert "注釈1: パネル3が無くなったため、パネル2に移しました。" in text
    assert page.input_value("#series-s2-panel") == "1"
    # 1×1 に戻しても値は変えない
    set_series_panel(page, "s2", 0)
    set_series_panel(page, "s2", 1)
    set_layout(page, 1, 1)
    assert series_state(page, "s2")["panel"] == 1


def test_share_checkboxes_disabled_for_category_axes_and_bar_types(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    set_layout(page, 2, 1)
    assert not is_disabled(page, "layoutShareX") and not is_disabled(page, "layoutShareY")
    assert is_hidden_by_id(page, "layoutShareHelp")
    page.check("#layoutShareX")
    wait_settled(page)
    page.select_option("#plotType", "bar")
    wait_settled(page)
    assert is_disabled(page, "layoutShareX") and not is_disabled(page, "layoutShareY")
    assert not is_hidden_by_id(page, "layoutShareHelp")
    assert panel_state(page)["layout"]["shareX"] is True  # 値は消さない
    page.select_option("#plotType", "barh")
    wait_settled(page)
    assert not is_disabled(page, "layoutShareX") and is_disabled(page, "layoutShareY")
    for kind in ("box", "violin"):
        page.select_option("#plotType", kind)
        wait_settled(page)
        assert is_disabled(page, "layoutShareX")


def test_bar_uses_category_kind_in_multi_panel(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, "categories.csv", plot_type="bar")
    ann = add_annotation(page, "vline", x="1")
    assert page.get_attribute(f"#annotation-{ann}-x", "placeholder") == "例 1.5"  # 1×1 は従来どおり
    set_layout(page, 1, 2)
    assert page.get_attribute(f"#annotation-{ann}-x", "placeholder") == "何番目か（0 始まり）"
    assert status_kind(page) != "error"
    set_layout(page, 1, 1)
    assert page.get_attribute(f"#annotation-{ann}-x", "placeholder") == "例 1.5"


def test_x_kind_mismatch_between_panels_errors_and_recovers(page, app_url, fixtures_dir, console_log):
    # datetime.csv: 列1 は文字列（ID）、列2 は数値（通番）、列3 は温度
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "datetime.csv")
    wait_settled(page)
    page.select_option("#series-s1-x", "__idx__2")
    page.select_option("#series-s1-y", "__idx__3")
    add_second_series(page, y="__idx__4", x="__idx__1")
    set_layout(page, 1, 2, wait=False)
    set_series_panel(page, "s2", 1)
    wait_error_status(page)
    assert "X の種類" in status_text(page)
    page.select_option("#series-s2-x", "__idx__2")
    wait_settled(page)
    assert status_kind(page) != "error"
    assert len(image_summary(page)) == 2


def test_edit_mode_layout_change_does_not_redraw(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    wait_code_generated(page)
    enter_edit_mode(page)
    generation, code = image_generation(page), code_text(page)
    set_layout(page, 2, 2, wait=False)
    page.wait_for_timeout(800)
    assert image_generation(page) == generation and code_text(page) == code
    assert len(image_summary(page)) == 1
    assert "編集" in status_text(page)


def test_narrow_screen_has_no_horizontal_scroll(page, app_url, fixtures_dir, console_log):
    page.set_viewport_size({"width": 375, "height": 800})
    start(page, app_url, fixtures_dir)
    add_second_series(page)
    page.check("#series-s2-use-y2")
    set_layout(page, 2, 2)
    set_series_panel(page, "s2", 3)
    add_annotation(page, "text", text="注", x="1", y="2")
    page.evaluate("document.getElementById('panelLabelsGroup').open = true")
    wait_settled(page)
    overflow = page.evaluate(
        """() => {
          const wide = [...document.querySelectorAll('.annotation-item, .series-item, .panel-label-row, #layoutGroup')]
            .filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.id || e.className);
          return {page: document.documentElement.scrollWidth - window.innerWidth, wide};
        }"""
    )
    assert overflow["page"] <= 0 and overflow["wide"] == []
