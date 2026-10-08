"""D1: ファイルのドロップ（ページ全体）、表の貼り付け、貼り付けたデータの保存、.tsv。"""
import pytest

from helpers import (
    code_text,
    drag_event,
    drop_files,
    drop_overlay_visible,
    enter_edit_mode,
    load_count,
    open_code_tab,
    paste_text,
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
    EXCEL_TABLE,
)

pytestmark = pytest.mark.e2e

NOT_A_TABLE = "貼り付けた内容が表ではありません。Excel などで表の範囲をコピーしてから貼り付けてください。"


@pytest.fixture
def start(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    return page


def fixture_file(fixtures_dir, name):
    return (name, (fixtures_dir / name).read_bytes())


def drop_and_wait(page, files, selector="body"):
    before = load_count(page)
    drop_files(page, files, selector)
    wait_load_count(page, before + 1)
    wait_settled(page)


def test_drop_csv_loads_and_plots(start, fixtures_dir):
    page = start
    assert not drop_overlay_visible(page)
    assert page.get_attribute("#dropOverlay", "aria-hidden") == "true"
    drop_and_wait(page, [fixture_file(fixtures_dir, "utf8.csv")])
    assert page.get_attribute("html", "data-data-state") == "ready"
    assert "utf8.csv" in page.inner_text("#fileNameLabel")
    assert plot_src(page).startswith("data:image/png")
    assert not drop_overlay_visible(page)


def test_overlay_shows_during_dragover_and_hides_after_drop(start, fixtures_dir):
    page = start
    files = [fixture_file(fixtures_dir, "utf8.csv")]
    drag_event(page, "dragenter", "body", files)
    prevented = drag_event(page, "dragover", "#plotArea", files)
    assert prevented  # ブラウザがファイルを開かない
    assert drop_overlay_visible(page)
    assert page.get_attribute("#dropOverlay", "aria-hidden") == "false"
    assert "ここにドロップして読み込む" in page.inner_text("#dropOverlay")
    # 子要素への出入りでちらつかない（enter 2 回、leave 1 回では出たまま）
    drag_event(page, "dragenter", "#title", files)
    drag_event(page, "dragleave", "#plotArea", files)
    assert drop_overlay_visible(page)
    before = load_count(page)
    assert drag_event(page, "drop", "#plotArea", files)
    assert not drop_overlay_visible(page)
    wait_load_count(page, before + 1)


def test_overlay_hides_on_leave_and_escape(start, fixtures_dir):
    page = start
    files = [fixture_file(fixtures_dir, "utf8.csv")]
    drag_event(page, "dragenter", "body", files)
    assert drop_overlay_visible(page)
    drag_event(page, "dragleave", "body", files)
    assert not drop_overlay_visible(page)
    drag_event(page, "dragenter", "body", files)
    assert drop_overlay_visible(page)
    page.keyboard.press("Escape")
    assert not drop_overlay_visible(page)


def test_text_drag_does_not_show_overlay(start):
    page = start
    drag_event(page, "dragenter", "body", text="hello")
    prevented = drag_event(page, "dragover", "body", text="hello")
    assert not drop_overlay_visible(page)
    assert not prevented  # 文字列のドラッグには手を出さない
    drag_event(page, "drop", "#title", text="hello")
    assert page.get_attribute("html", "data-data-state") == "none"


def test_drop_two_files_loads_both(start, fixtures_dir):
    page = start
    drop_and_wait(page, [fixture_file(fixtures_dir, "utf8.csv"), fixture_file(fixtures_dir, "growth.csv")])
    assert "utf8.csv ほか 1 件" in page.inner_text("#fileNameLabel")
    assert page.locator("#fileList .file-row").count() == 2
    assert status_warnings(page) == []


def test_drop_on_code_textarea_loads_instead_of_navigating(start, fixtures_dir):
    page = start
    url = page.url
    drop_and_wait(page, [fixture_file(fixtures_dir, "utf8.csv")], "#customPyCode")
    assert page.url == url and page.get_attribute("html", "data-data-state") == "ready"


def test_drop_unsupported_extension_shows_loader_error(start):
    page = start
    drop_files(page, [("memo.json", b"{}")])
    page.wait_for_function("document.documentElement.dataset.dataState === 'error'")
    assert status_kind(page) == "error" and "対応していない拡張子" in status_text(page)


def test_drop_without_files_warns(start):
    page = start
    page.evaluate(
        """() => {
          const dt = new DataTransfer();
          dt.items.add(new File([''], 'x.csv'));
          dt.items.clear();
          const e = new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true});
          Object.defineProperty(dt, 'types', {value: ['Files']});
          document.body.dispatchEvent(e);
        }"""
    )
    assert status_kind(page) == "warning" and "読み込めるファイルが見つかりません" in status_text(page)


def test_tsv_file_loads_with_tab_separator(start):
    page = start
    drop_and_wait(page, [("data.tsv", "x\ty\n1\t2\n2\t4\n3\t9\n".encode())])
    assert page.inner_text("#series-s1-y").count("[") >= 2
    assert page.get_attribute("html", "data-data-state") == "ready"
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    text = code_text(page)
    assert 'sep="\\t"' in text and "TSV（.tsv）" in text and "貼り付けたデータ" not in text


def test_file_input_accepts_tsv(start):
    page = start
    assert ".tsv" in page.get_attribute("#fileInput", "accept")
    assert ".tsv" in page.inner_text("label[for=fileInput]")


def paste_and_wait(page, text, selector="#pasteArea"):
    before = load_count(page)
    paste_text(page, text, selector)
    wait_load_count(page, before + 1)
    wait_settled(page)


def test_paste_excel_table_loads_and_plots(start):
    page = start
    assert page.is_hidden("#savePastedBtn")
    assert paste_text(page, EXCEL_TABLE) is True  # 貼り付けの既定動作は止める
    wait_data_ready(page)
    wait_settled(page)
    assert page.input_value("#pasteArea") == ""
    assert "貼り付けたデータ" in page.inner_text("#fileNameLabel")
    assert "時間 [0]" in page.inner_text("#series-s1-y")
    assert plot_src(page).startswith("data:image/png")
    assert page.is_visible("#savePastedBtn")


def test_paste_replaces_current_data(start, fixtures_dir):
    page = start
    page.set_input_files("#fileInput", str(fixtures_dir / "utf8.csv"))
    wait_data_ready(page)
    wait_settled(page)
    paste_and_wait(page, "a\tb\n1\t2\n3\t4\n")
    assert "a [0]" in page.inner_text("#series-s1-y")


def test_input_event_with_value_is_treated_as_paste(start):
    page = start
    before = load_count(page)
    page.evaluate(
        """(t) => { const a = document.getElementById('pasteArea'); a.value = t; a.dispatchEvent(new Event('input', {bubbles: true})); }""",
        EXCEL_TABLE,
    )
    wait_load_count(page, before + 1)
    assert page.input_value("#pasteArea") == ""


def test_document_level_paste_with_body_focus(start):
    page = start
    page.evaluate("document.activeElement && document.activeElement.blur()")
    paste_and_wait(page, EXCEL_TABLE, selector=None)
    assert page.get_attribute("html", "data-data-state") == "ready"
    assert "貼り付けたデータ" in page.inner_text("#fileNameLabel")


def test_paste_into_title_is_a_normal_paste(start):
    page = start
    assert paste_text(page, EXCEL_TABLE, "#title") is False
    page.wait_for_timeout(500)
    assert page.get_attribute("html", "data-data-state") == "none"
    assert load_count(page) == 0


def test_non_table_text_warns_and_loads_nothing(start):
    page = start
    paste_text(page, "ただの一行の文章です")
    assert status_kind(page) == "warning" and status_text(page) == NOT_A_TABLE
    assert page.get_attribute("html", "data-data-state") == "none"
    paste_text(page, "   \n \n")
    assert status_text(page) == NOT_A_TABLE


def test_two_lines_without_tabs_count_as_a_table(start):
    page = start
    paste_and_wait(page, "a,b\n1,2\n3,4\n")
    assert page.get_attribute("html", "data-data-state") == "ready"


def test_code_tab_shows_pasted_file_and_comment(start):
    page = start
    paste_and_wait(page, EXCEL_TABLE)
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    text = code_text(page)
    assert 'DATA_FILE = "pasted_data.tsv"' in text
    assert "# 貼り付けたデータ: 「データ読み込み」の「貼り付けたデータを保存」で pasted_data.tsv を保存し、このスクリプトと同じフォルダに置いてください。" in text
    assert 'sep="\\t"' in text


def test_save_pasted_downloads_identical_bytes(start):
    page = start
    paste_and_wait(page, EXCEL_TABLE)
    with page.expect_download() as dl:
        page.click("#savePastedBtn")
    assert dl.value.suggested_filename == "pasted_data.tsv"
    data = open(dl.value.path(), "rb").read()
    assert data == EXCEL_TABLE.replace("\r\n", "\n").encode("utf-8")  # 改行は LF にそろえて読み込む


def test_save_button_hides_when_a_file_replaces_pasted_data(start, fixtures_dir):
    page = start
    paste_and_wait(page, EXCEL_TABLE)
    assert page.is_visible("#savePastedBtn")
    page.set_input_files("#fileInput", str(fixtures_dir / "utf8.csv"))
    wait_settled(page)
    assert page.is_hidden("#savePastedBtn")
    assert "貼り付けたデータ" not in page.inner_text("#fileNameLabel")


def test_edit_mode_code_can_read_pasted_file(start):
    page = start
    paste_and_wait(page, EXCEL_TABLE)
    enter_edit_mode(page)
    page.fill(
        "#customPyCode",
        "import pandas as pd\nimport matplotlib.pyplot as plt\n"
        "df = pd.read_csv('pasted_data.tsv', sep='\\t')\n"
        "fig, ax = plt.subplots()\nax.plot(df.iloc[:, 0], df.iloc[:, 1])\nprint('rows', len(df))\n",
    )
    run_edited_code(page)
    assert "rows 4" in page.inner_text("#codeOutput")
