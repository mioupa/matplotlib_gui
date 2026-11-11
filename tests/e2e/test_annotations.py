"""注釈（Phase 5b, G4）: 種類ごとの描画、入力欄の出し分け、日時・文字列の X、第2Y軸、凡例、エラーと復帰。"""
import pytest

from helpers import (
    add_annotation,
    code_is_stale,
    code_text,
    enter_edit_mode,
    image_generation,
    add_fit,
    code_value,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    set_annotation,
    state_list,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e

X, MEAN, DAY, OTHER = "__idx__0", "__idx__1", "__idx__4", "__idx__5"


def start(page, app_url, fixtures_dir, fixture="band.csv", x=X, y=MEAN, plot_type=None):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    if plot_type:
        page.select_option("#plotType", plot_type)
    page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", y)
    wait_settled(page)


def counts(page, axis=0):
    return image_summary(page)[axis]["annotations"]


def test_section_and_every_kind_numeric_x(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    titles = page.eval_on_selector_all("aside.panel > details.panel-section > summary", "els => els.map(e => e.textContent.trim())")
    assert titles.index("注釈・解析") == titles.index("体裁") + 1 == titles.index("保存") - 1
    assert page.is_visible("#addAnnotationBtn") and page.inner_text("#addAnnotationBtn") == "+ 注釈を追加"
    h = add_annotation(page, "hline", y="10", label="基準値")
    # 種類ごとに出る欄が違う
    visible = lambda aid, name: not is_hidden_by_id(page, f"annotation-{aid}-{name}")  # noqa: E731
    assert visible(h, "y") and visible(h, "line-style") and visible(h, "label") and visible(h, "alpha")
    assert not visible(h, "x") and not visible(h, "text") and not visible(h, "start") and not visible(h, "axis")
    assert page.get_attribute(f"#annotation-{h}-y", "placeholder") == "例 1.5"
    v = add_annotation(page, "vline", x="5")
    sp = add_annotation(page, "vspan", start="2", end="4", label="区間")
    hs = add_annotation(page, "hspan", start="5", end="8")
    t = add_annotation(page, "text", text="ピーク", x="3", y="8")
    assert visible(t, "text") and visible(t, "coords") and visible(t, "font-size") and not visible(t, "line-style") and not visible(t, "label")
    wait_settled(page)
    wait_code_generated(page)
    assert counts(page) == {"texts": 1, "hlines": 1, "vlines": 1, "hspans": 1, "vspans": 1}
    legend = image_summary(page)[0]["legend"]
    assert "基準値" in legend and "区間" in legend
    code = code_value(page)
    assert "ax.axhline(" in code and "ax.axvspan(" in code and "ax.text(" in code
    # 文字の位置を「図の中の割合」にすると、例が 0〜1 になる
    set_annotation(page, t, coords="axes", x="0.05", y="0.95")
    wait_settled(page)
    assert page.get_attribute(f"#annotation-{t}-x", "placeholder") == "0〜1" and "transAxes" in code_value(page)
    # 削除で消える（id は再利用しない）
    page.click(f"#annotation-{sp}-remove")
    wait_settled(page)
    assert counts(page)["vspans"] == 0 and [a["id"] for a in state_list(page, "annotations")] == [h, v, hs, t]
    assert add_annotation(page, "hline", y="1") == "a6"
    wait_settled(page)
    # 入力のエラー: 数として読めない Y。コードタブは「最新でない」、直すと復帰
    set_annotation(page, h, y="abc")
    wait_error_status(page)
    assert "注釈1" in status_text(page) and code_is_stale(page)
    set_annotation(page, h, y="12")
    wait_settled(page)
    wait_code_generated(page)
    assert status_kind(page) != "error" and not code_is_stale(page)


def test_datetime_and_category_x_and_secondary_axis(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir, x=DAY)
    v = add_annotation(page, "vline", x="2026-01-05 12:00")
    assert page.get_attribute(f"#annotation-{v}-x", "placeholder") == "例 2026-01-31 12:00"
    wait_settled(page)
    assert counts(page)["vlines"] == 1 and "pd.Timestamp(" in code_value(page)
    set_annotation(page, v, x="5")  # 日時の X に数を入れるとエラー
    wait_error_status(page)
    assert "注釈1" in status_text(page)
    # 第2Y軸: 使うときだけ「Y 軸」の欄が出る。右の軸の水平線は ax2 に描く
    page.select_option("#series-s1-x", X)
    h = add_annotation(page, "hline", y="50")
    set_annotation(page, v, x="3")
    wait_settled(page)
    assert is_hidden_by_id(page, f"annotation-{h}-axis")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", X)
    page.select_option("#series-s2-y", OTHER)
    page.check("#series-s2-use-y2")
    wait_settled(page)
    assert not is_hidden_by_id(page, f"annotation-{h}-axis") and is_hidden_by_id(page, f"annotation-{v}-axis")
    set_annotation(page, h, axis="y2")
    wait_settled(page)
    assert len(image_summary(page)) == 2
    assert counts(page, 1)["hlines"] == 1 and counts(page, 0)["hlines"] == 0
    # 文字列の X: 位置は何番目か（0 始まり）
    load_fixture(page, fixtures_dir / "categories.csv")
    wait_settled(page)
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)
    assert page.get_attribute(f"#annotation-{v}-x", "placeholder") == "何番目か（0 始まり）"
    set_annotation(page, v, x="1.5")
    wait_settled(page)
    assert status_kind(page) != "error" and counts(page)["vlines"] == 1


def test_edit_mode_does_not_redraw_for_annotations_or_fits(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    wait_code_generated(page)
    enter_edit_mode(page)
    generation, code = image_generation(page), code_text(page)
    add_annotation(page, "hline", y="10")
    add_fit(page)
    page.wait_for_timeout(800)  # 再描画の遅延（250 ms）より長く待つ
    assert image_generation(page) == generation and code_text(page) == code
    assert image_summary(page)[0]["annotations"]["hlines"] == 0
    assert "編集" in status_text(page)


def test_narrow_screen_has_no_horizontal_scroll(page, app_url, fixtures_dir, console_log):
    page.set_viewport_size({"width": 375, "height": 800})
    start(page, app_url, fixtures_dir)
    add_annotation(page, "text", text="ピーク", x="3", y="8")
    add_annotation(page, "vspan", start="2", end="4", label="区間")
    add_fit(page, model="poly")
    page.click("#series-s1-duplicate")
    wait_settled(page)
    overflow = page.evaluate(
        """() => {
          const wide = [...document.querySelectorAll('.annotation-item, .fit-item, .series-item')]
            .filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.id || e.className);
          return {page: document.documentElement.scrollWidth - window.innerWidth, wide};
        }"""
    )
    assert overflow["page"] <= 0 and overflow["wide"] == []
