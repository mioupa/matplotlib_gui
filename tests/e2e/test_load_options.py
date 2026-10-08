"""データ取り込みの設定（D2 シート / D3 ヘッダより前の行 / D4 桁区切り・小数点・コメント）と、コードの「最新でない」表示。"""
import pytest

from helpers import (
    change_load_option,
    code_generation,
    code_is_stale,
    code_text,
    enter_edit_mode,
    image_generation,
    image_summary,
    load_count,
    load_fixture,
    open_code_tab,
    plot_src,
    set_load_options,
    set_save_dpi,
    sheet_options,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_generated,
    wait_code_contains,
    wait_settled,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def start(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    return page


def select_xy(page, x="__idx__0", y="__idx__1"):
    page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", y)
    wait_settled(page)


def test_second_sheet_changes_columns_plot_and_code(start, fixtures_dir):
    page = start
    assert not page.is_visible("#sheetGroup")
    load_fixture(page, fixtures_dir / "multi_sheet.xlsx")
    wait_settled(page)
    assert page.is_visible("#sheetGroup") and sheet_options(page) == ["Sheet1", "二枚目"]
    assert page.input_value("#sheetSelect") == "Sheet1"
    assert "時間 [0]" in page.inner_text("#series-s1-y")
    before = plot_src(page)
    change_load_option(page, lambda: page.select_option("#sheetSelect", "二枚目"))
    assert page.input_value("#sheetSelect") == "二枚目"
    options = page.inner_text("#series-s1-y")
    assert "z [2]" in options and "時間 [0]" not in options
    select_xy(page)
    wait_code_generated(page)
    open_code_tab(page)
    assert 'sheet_name="二枚目",' in code_text(page)
    assert plot_src(page) != before
    # 新しいファイルを選ぶと先頭のシートに戻る
    load_fixture(page, fixtures_dir / "preamble.xlsx")
    wait_settled(page)
    assert page.input_value("#sheetSelect") == "データ" and sheet_options(page) == ["データ", "説明つき"]
    # CSV ではシートの欄は出ない
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    assert not page.is_visible("#sheetGroup")


def test_preamble_needs_skip_lines_and_is_shown(start, fixtures_dir):
    page = start
    page.set_input_files("#fileInput", str(fixtures_dir / "preamble.csv"))
    page.wait_for_function("document.documentElement.dataset.dataState === 'error'")
    assert status_kind(page) == "error" and "ヘッダより前に読み飛ばす行数" in status_text(page)
    change_load_option(page, lambda: page.fill("#skipLines", "3"))
    assert status_kind(page) == "ok"
    page.click("#tabDataBtn")
    box = page.inner_text("#dataPreamble")
    assert "ヘッダより前に読み飛ばした行（3行）" in box and "装置: テスト用ロガー" in box and "備考: この行はデータではありません" in box
    assert "…ほか" not in box
    assert "時間 [0]" in page.inner_text("#series-s1-y")
    # 0 に戻すと説明の行は出ない（読み込みはまた失敗する）
    page.fill("#skipLines", "0")
    page.wait_for_function("document.documentElement.dataset.dataState === 'error'")


def test_preamble_box_for_xlsx_and_overflow(start, fixtures_dir):
    page = start
    set_load_options(page, skip_lines=2)
    load_fixture(page, fixtures_dir / "multi_sheet.xlsx")  # 先頭シートは見出しが1行目なので、2行読み飛ばすと見出しがデータ行になる
    wait_settled(page)
    page.click("#tabDataBtn")
    assert "ヘッダより前に読み飛ばした行（2行）" in page.inner_text("#dataPreamble")
    change_load_option(page, lambda: page.select_option("#sheetSelect", "二枚目"))
    assert "ヘッダより前に読み飛ばした行（2行）" in page.inner_text("#dataPreamble")


def test_european_numbers_are_plotted(start, fixtures_dir):
    page = start
    set_load_options(page, delimiter=";", thousands=".", decimal=",")
    load_fixture(page, fixtures_dir / "european.csv")
    wait_settled(page)
    select_xy(page)
    summary = image_summary(page)
    assert summary[0]["lines"] == 1 and summary[0]["ylim"][1] > 1000


def test_european_numbers_without_settings_get_a_hint(start, fixtures_dir):
    page = start
    set_load_options(page, delimiter=";")
    load_fixture(page, fixtures_dir / "european.csv")
    wait_settled(page)
    select_xy(page)
    # 数値が1つも読めないので、案内つきのエラーになる
    assert status_kind(page) == "error" and "「小数点」をカンマ" in status_text(page), status_text(page)
    change_load_option(page, lambda: page.select_option("#decimal", ","))
    assert "小数点" not in status_text(page)


def test_comment_character(start, fixtures_dir):
    page = start
    set_load_options(page, comment="#")
    load_fixture(page, fixtures_dir / "comments.csv")
    wait_settled(page)
    select_xy(page)
    summary = image_summary(page)
    assert summary[0]["lines"] == 1
    page.click("#tabDataBtn")
    assert "行数: 10" in page.inner_text("#dataArea")


def test_thousands_warning_hint_and_fix(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "thousands.csv")
    wait_settled(page)
    select_xy(page, "__idx__0", "__idx__1")
    assert status_kind(page) == "error" and "「桁区切り」をカンマ" in status_text(page), status_text(page)
    change_load_option(page, lambda: page.select_option("#thousands", ","))
    assert "桁区切り" not in status_text(page)
    assert image_summary(page)[0]["ylim"][1] > 10000


def test_code_follows_load_settings_in_sync_mode(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    assert "skiprows=0," in code_text(page) and "thousands=None," in code_text(page)
    for action, expected in (
        (lambda: page.fill("#skipLines", "1"), "skiprows=1,"),
        (lambda: page.select_option("#decimal", ","), 'decimal=",",'),
        (lambda: page.select_option("#thousands", "."), 'thousands=".",'),
        (lambda: page.fill("#commentChar", "%"), 'comment="%",'),
    ):
        change_load_option(page, action)
        wait_code_generated(page)
        assert expected in code_text(page)
        assert code_generation(page) == image_generation(page)


def test_edit_mode_keeps_code_when_load_settings_change(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)
    enter_edit_mode(page)
    code = code_text(page)
    count = load_count(page)
    page.fill("#skipLines", "1")
    page.wait_for_function(f"Number(document.documentElement.dataset.loadCount) > {count}")
    assert code_text(page) == code
    assert "編集中" in status_text(page)


def test_stale_note_for_render_error_and_recovery(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    assert not code_is_stale(page)
    good = code_text(page)
    page.fill("#subplotLeft", "0.9")
    page.fill("#subplotRight", "0.1")
    page.fill("#subplotBottom", "0.1")
    page.fill("#subplotTop", "0.9")
    wait_settled(page)
    assert status_kind(page) == "error"
    page.wait_for_function("document.getElementById('customPyCode').dataset.stale === 'true'")
    assert code_is_stale(page) and "最新の設定を反映していません" in page.inner_text("#codeStaleNote")
    assert code_text(page) == good  # 表示中のコードは変わらない
    page.fill("#subplotRight", "0.95")
    wait_settled(page)
    wait_code_generated(page)
    assert not code_is_stale(page)
    assert "subplots_adjust(left=0.9" in code_text(page)


def test_stale_note_for_script_refresh_error_and_edit_mode(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    set_save_dpi(page, 99999)  # 保存設定の不正: コードの更新だけが失敗する
    page.wait_for_function("document.getElementById('customPyCode').dataset.stale === 'true'")
    assert code_is_stale(page) and status_kind(page) == "error"
    set_save_dpi(page, 150)
    wait_code_contains(page, "dpi=150")
    assert not code_is_stale(page)
    set_save_dpi(page, 99999)
    page.wait_for_function("document.getElementById('customPyCode').dataset.stale === 'true'")
    enter_edit_mode(page)
    assert not code_is_stale(page)
