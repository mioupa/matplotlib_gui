"""D6: 複数ファイル（追加・置き換え・削除、データ元、データ確認の切替、一部の失敗、編集モード、ドロップ）。"""
import pytest

from helpers import (
    add_files,
    add_series_with_source,
    code_text,
    drop_files,
    enter_edit_mode,
    file_row_ids,
    file_row_states,
    image_summary,
    load_count,
    load_fixture,
    open_code_tab,
    plot_src,
    run_edited_code,
    status_kind,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_code_generated,
    wait_data_ready,
    wait_load_count,
    wait_settled,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def start(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    return page


def two_files(page, fixtures_dir, first="utf8.csv", second="growth.csv"):
    load_fixture(page, fixtures_dir / first)
    wait_settled(page)
    add_files(page, [fixtures_dir / second])


def test_single_file_display_has_no_list_or_source_select(start, fixtures_dir):
    page = start
    assert not page.is_visible("#fileList") and not page.is_visible("#previewSource")
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    assert not page.is_visible("#fileList") and not page.is_visible("#series-s1-source")
    assert "UTF-8" in page.inner_text("#encodingLabel") and page.inner_text("#fileNameLabel") == "utf8.csv"
    assert page.get_attribute("#fileInput", "multiple") is not None and page.get_attribute("#addFileInput", "multiple") is not None


def test_add_second_file_two_series_from_different_files(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    assert file_row_states(page) == {"file-d1": "ready", "file-d2": "ready"}
    assert page.inner_text("#fileNameLabel") == "utf8.csv ほか 1 件"
    assert page.inner_text("#encodingLabel") == "" and not page.is_visible("#sheetGroup")
    assert "データ1" in page.inner_text("#file-d1") and "growth.csv" in page.inner_text("#file-d2")
    assert page.is_visible("#series-s1-source")
    assert page.inner_text("#series-s1-source") == "データ1: utf8.csv\nデータ2: growth.csv"
    assert page.get_attribute("html", "data-data-state") == "ready"
    add_series_with_source(page, "d2", "__idx__2")
    wait_code_generated(page)
    summary = image_summary(page)
    assert summary[0]["lines"] == 2
    # 系列2のY列の選択肢は growth.csv の列
    assert "指数 [1]" in page.inner_text("#series-s2-y") and "電圧" not in page.inner_text("#series-s2-y")
    assert "電圧 [1]" in page.inner_text("#series-s1-y")
    open_code_tab(page)
    text = code_text(page)
    for needle in ("DATA_FILE_1", "DATA_FILE_2", "df2.iloc[:, 2]", "df1.iloc[:, 0]"):
        assert needle in text
    assert "「utf8.csv」「growth.csv」" in text


def test_changing_series_source_resets_columns(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__2")
    page.select_option("#series-s1-source", "d2")
    assert page.input_value("#series-s1-x") == "" and page.input_value("#series-s1-y") == ""
    wait_settled(page)
    assert "指数 [1]" in page.inner_text("#series-s1-y")


def test_preview_source_switches_the_table(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    assert page.is_visible("#previewSource") is False  # データ確認タブを開くまでは見えない
    page.click("#tabDataBtn")
    assert page.is_visible("#previewSource")
    assert "電圧" in page.inner_text("#dataArea")
    page.select_option("#previewSource", "d2")
    assert "指数" in page.inner_text("#dataArea") and "電圧" not in page.inner_text("#dataArea")
    page.fill("#skipRows", "2")
    assert page.locator("#dataArea tbody tr.skipped-row").count() == 2


def test_remove_file_resets_series_and_returns_to_single_display(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    add_series_with_source(page, "d2", "__idx__2")
    page.click("#file-d2-remove")
    wait_settled(page)
    assert not page.is_visible("#fileList") and not page.is_visible("#series-s1-source")
    assert page.inner_text("#fileNameLabel") == "utf8.csv" and "UTF-8" in page.inner_text("#encodingLabel")
    assert page.input_value("#series-s2-y") == ""
    assert "データ2（growth.csv）を削除したため、系列2の列を自動に戻しました。" in status_warnings(page)
    assert image_summary(page)[0]["lines"] == 2  # 系列2は先頭ファイルの自動列で描かれる
    page.click("#tabCodeBtn")
    wait_code_generated(page)
    assert "DATA_FILE =" in code_text(page) and "DATA_FILE_2" not in code_text(page)


def test_remove_first_file_resets_series_using_it(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    page.select_option("#series-s1-y", "__idx__2")
    wait_settled(page)
    page.click("#file-d1-remove")
    wait_settled(page)
    assert page.inner_text("#fileNameLabel") == "growth.csv"
    assert page.input_value("#series-s1-y") == ""
    assert "データ1（utf8.csv）を削除したため、系列1の列を自動に戻しました。" in status_warnings(page)


def test_replace_with_two_files_via_file_input(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    add_series_with_source(page, "d2", "__idx__2")
    before = load_count(page)
    page.set_input_files("#fileInput", [str(fixtures_dir / "categories.csv"), str(fixtures_dir / "tab.txt")])
    wait_load_count(page, before + 1)
    wait_settled(page)
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    assert "categories.csv" in page.inner_text("#file-d1") and "tab.txt" in page.inner_text("#file-d2")
    assert page.input_value("#series-s2-source") == "d1"  # データ元は先頭に戻る


def test_same_name_file_replaces_the_entry(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    add_files(page, [fixtures_dir / "growth.csv"])
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    add_files(page, [fixtures_dir / "tab.txt"])
    assert file_row_ids(page) == ["file-d1", "file-d2", "file-d3"]


def test_more_than_ten_files_warns(start, fixtures_dir):
    page = start
    files = [(f"f{i}.csv", b"a,b\n1,2\n3,4\n5,7\n") for i in range(12)]
    before = load_count(page)
    drop_files(page, files)
    wait_load_count(page, before + 1)
    wait_settled(page)
    assert len(file_row_ids(page)) == 10
    assert "読み込めるファイルは10個までです。先頭から10個を読み込みました。" in status_warnings(page)


def test_drop_add_and_replace_zones(start, fixtures_dir):
    page = start
    csv = lambda name: (name, (fixtures_dir / name).read_bytes())  # noqa: E731
    before = load_count(page)
    drop_files(page, [csv("utf8.csv")])
    wait_load_count(page, before + 1)
    wait_settled(page)
    from helpers import drag_event, drop_overlay_visible

    drag_event(page, "dragenter", "body", [csv("growth.csv")])
    assert drop_overlay_visible(page)
    assert page.is_visible("#dropReplace") and page.is_visible("#dropAdd") and not page.is_visible("#dropLoad")
    drag_event(page, "dragover", "#dropAdd", [csv("growth.csv")])
    assert "drop-zone-active" in page.get_attribute("#dropAdd", "class")
    drag_event(page, "drop", "#dropAdd", [csv("growth.csv")])
    wait_load_count(page, before + 2)
    wait_settled(page)
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    drag_event(page, "dragenter", "body", [csv("tab.txt")])
    drag_event(page, "drop", "#dropReplace", [csv("tab.txt")])
    wait_load_count(page, before + 3)
    wait_settled(page)
    assert file_row_ids(page) == [] and page.inner_text("#fileNameLabel") == "tab.txt"


def test_one_file_failing_keeps_the_other_and_recovers(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    before = load_count(page)
    page.set_input_files("#addFileInput", [str(fixtures_dir / "growth.csv")])
    wait_load_count(page, before + 1)
    wait_settled(page)
    # 壊れた xlsx を足す（読み込めない）
    page.set_input_files("#addFileInput", [{"name": "broken.xlsx", "mimeType": "application/octet-stream", "buffer": b"not an excel file"}])
    page.wait_for_function("document.querySelector('#file-d3') && document.querySelector('#file-d3').dataset.state === 'error'")
    wait_settled(page)
    assert file_row_states(page) == {"file-d1": "ready", "file-d2": "ready", "file-d3": "error"}
    assert page.get_attribute("html", "data-data-state") == "error"
    assert page.inner_text("#file-d3 .file-row-error") != ""
    assert plot_src(page).startswith("data:image/png")  # ほかのファイルで描ける
    assert any("データ3（broken.xlsx）を読み込めませんでした" in w for w in status_warnings(page))
    assert status_kind(page) == "warning"
    # 失敗したファイルを使う系列はエラー
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-source", "d3")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "データ3（broken.xlsx）を読み込めていません" in status_text(page)
    # 削除すると復帰する
    page.click("#file-d3-remove")
    page.wait_for_function("document.documentElement.dataset.dataState === 'ready'")


def test_failed_file_is_retried_when_load_settings_change(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    semicolon = {"name": "semi.csv", "mimeType": "text/csv", "buffer": b"a;b\n1;2\n3;4\n5;7\n"}
    before = load_count(page)
    page.set_input_files("#addFileInput", [semicolon])
    wait_load_count(page, before + 1)
    wait_settled(page)
    assert file_row_states(page)["file-d2"] == "ready"
    page.fill("#delimiter", "x")  # どちらも区切れず、1列のまま
    page.wait_for_function("document.documentElement.dataset.dataState !== 'loading'")
    wait_settled(page)
    page.fill("#delimiter", "")
    page.wait_for_function("document.documentElement.dataset.dataState === 'ready'")
    wait_settled(page)
    assert file_row_states(page) == {"file-d1": "ready", "file-d2": "ready"}


def test_sheet_select_reloads_only_that_file(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    add_files(page, [fixtures_dir / "multi_sheet.xlsx"])
    assert page.is_visible("#file-d2-sheet") and not page.is_visible("#file-d1-sheet")
    assert page.inner_text("#file-d2") != "" and "Excel" in page.inner_text("#file-d2")
    page.evaluate(
        "() => { const orig = window.mplgui.loadFile; window.__ids = [];"
        "window.mplgui.loadFile = function () { window.__ids.push(arguments[3]); return orig.apply(this, arguments); }; }"
    )
    before = load_count(page)
    page.select_option("#file-d2-sheet", "二枚目")
    wait_load_count(page, before + 1)
    wait_settled(page)
    assert page.evaluate("window.__ids") == ["d2"]
    assert page.input_value("#file-d2-sheet") == "二枚目"
    page.select_option("#series-s1-source", "d2")
    wait_settled(page)
    assert "z [2]" in page.inner_text("#series-s1-y")
    wait_code_generated(page)
    open_code_tab(page)
    assert 'sheet_name="二枚目",' in code_text(page)


def test_edit_mode_reads_both_files_from_the_work_folder(start, fixtures_dir):
    page = start
    two_files(page, fixtures_dir)
    enter_edit_mode(page)
    page.fill(
        "#customPyCode",
        "import pandas as pd\nimport matplotlib.pyplot as plt\n"
        "a = pd.read_csv('utf8.csv')\nb = pd.read_csv('growth.csv')\n"
        "fig, ax = plt.subplots()\nax.plot(a.iloc[:, 0], a.iloc[:, 1])\nax.plot(b.iloc[:, 0], b.iloc[:, 1])\n",
    )
    run_edited_code(page)
    assert image_summary(page)[0]["lines"] == 2
    assert status_kind(page) == "ok"


def test_paste_replaces_all_files_and_keeps_save_button(start, fixtures_dir):
    from helpers import EXCEL_TABLE, paste_text

    page = start
    two_files(page, fixtures_dir)
    before = load_count(page)
    paste_text(page, EXCEL_TABLE)
    wait_load_count(page, before + 1)
    wait_settled(page)
    assert file_row_ids(page) == [] and page.is_visible("#savePastedBtn")
    add_files(page, [fixtures_dir / "growth.csv"])
    assert page.is_visible("#savePastedBtn")  # 貼り付けたデータが残っている間は出す
    assert file_row_ids(page) == ["file-d1", "file-d2"]
