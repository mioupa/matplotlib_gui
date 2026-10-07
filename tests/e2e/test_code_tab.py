"""Pythonコードタブ（P2〜P6）: 同期表示、コピー・.py 保存、編集と実行、GUI から再生成、エラーと出力の表示。"""
import pytest

from helpers import (
    code_generation,
    code_mode,
    code_output,
    code_output_kind,
    code_text,
    enter_edit_mode,
    image_generation,
    image_summary,
    load_fixture,
    open_code_tab,
    plot_src,
    run_edited_code,
    save_plot,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_generated,
    wait_run_finished,
    wait_settled,
)

pytestmark = pytest.mark.e2e

TITLE = "元タイトル"


@pytest.fixture
def app(page, app_url, fixtures_dir, console_log):
    """utf8.csv を読み込み、タイトルを設定して描画・コード生成まで済ませたページ。"""
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    page.fill("#title", TITLE)
    wait_settled(page)
    wait_code_generated(page)
    return page


def test_tab_label_and_generated_script_in_sync_mode(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    assert page.inner_text("#tabCodeBtn") == "Pythonコード"
    assert page.get_attribute("#customPyCode", "placeholder") == "ファイルを読み込むと、ここに Python コードが表示されます。"
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)
    open_code_tab(page)
    code = code_text(page)
    assert "import matplotlib.pyplot as plt" in code and 'DATA_FILE = "utf8.csv"' in code
    assert page.get_attribute("#customPyCode", "readonly") is not None
    assert code_mode(page) == "sync"
    assert "同期しています" in page.inner_text("#codeSyncStatus")
    assert page.is_visible("#editCodeBtn") and page.is_visible("#copyCodeBtn") and page.is_visible("#downloadCodeBtn")
    assert not page.is_visible("#applyCustomCodeBtn") and not page.is_visible("#resetCustomCodeBtn")
    assert not page.query_selector("#useCustomCode")
    assert page.get_attribute("#codeLineNumbers", "aria-hidden") == "true"
    assert page.inner_text("#codeLineNumbers").split("\n")[-1] == str(len(code.rstrip("\n").split("\n")) + 1)
    assert page.get_attribute("#codeOutput", "aria-live") == "polite"
    assert code_output(page) == ""  # 空のときの案内文は CSS（:empty::before）なので、テキストは空


def test_gui_change_updates_code_with_same_generation(app):
    page = app
    assert f'"{TITLE}"' in code_text(page)
    page.fill("#title", "新しいタイトル")
    wait_settled(page)
    wait_code_generated(page)
    assert '"新しいタイトル"' in code_text(page) and TITLE not in code_text(page)
    assert code_generation(page) == image_generation(page)
    assert image_summary(page)[0]["title"] == "新しいタイトル"


def test_copy_button_copies_textarea(app):
    page = app
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_code_tab(page)
    page.click("#copyCodeBtn")
    page.wait_for_function("document.getElementById('status').textContent.includes('コピーしました')")
    assert status_text(page) == "Pythonコードをコピーしました。"
    assert page.evaluate("navigator.clipboard.readText()") == code_text(page)


def test_download_py_uses_save_filename_rules(app):
    page = app
    open_code_tab(page)
    with page.expect_download() as dl:
        page.click("#downloadCodeBtn")
    download = dl.value
    assert download.suggested_filename == "plot.py"
    assert open(download.path(), encoding="utf-8").read() == code_text(page)
    assert status_text(page) == "Pythonコードを保存しました: plot.py"

    page.fill("#saveFilename", "my fig.png")
    with page.expect_download() as dl2:
        page.click("#downloadCodeBtn")
    assert dl2.value.suggested_filename == "my fig.py"


def test_edit_and_run_changes_the_figure(app):
    page = app
    before = image_generation(page)
    enter_edit_mode(page)
    assert code_mode(page) == "edit"
    assert page.get_attribute("#customPyCode", "readonly") is None
    assert "同期していません" in page.inner_text("#codeSyncStatus")
    assert page.is_visible("#applyCustomCodeBtn") and page.is_visible("#resetCustomCodeBtn") and not page.is_visible("#editCodeBtn")
    assert page.evaluate("document.activeElement.id") == "customPyCode"

    page.fill("#customPyCode", code_text(page).replace(TITLE, "編集後のタイトル"))
    gen = run_edited_code(page, "button")
    assert gen != before
    assert status_kind(page) == "ok" and status_text(page).startswith("コードの実行に成功しました")
    assert image_summary(page)[0]["title"] == "編集後のタイトル"
    assert code_output_kind(page) == "ok"


def test_gui_change_in_edit_mode_is_not_applied_until_regenerate(app):
    page = app
    enter_edit_mode(page)
    edited = code_text(page) + "\n# 編集中のメモ\n"
    page.fill("#customPyCode", edited)
    gen = image_generation(page)
    src = plot_src(page)
    page.fill("#title", "編集中に変えたタイトル")
    page.wait_for_timeout(1200)  # デバウンス（250ms）を十分に超えて待つ
    assert code_text(page) == edited
    assert image_generation(page) == gen and plot_src(page) == src
    assert status_kind(page) == "warning" and "編集中のため" in status_text(page)
    assert "同期していません" in page.inner_text("#codeSyncStatus")

    page.click("#resetCustomCodeBtn")
    assert code_mode(page) == "sync"
    assert page.get_attribute("#customPyCode", "readonly") is not None
    wait_settled(page)
    wait_code_generated(page)
    assert '"編集中に変えたタイトル"' in code_text(page) and "編集中のメモ" not in code_text(page)
    assert image_generation(page) != gen
    assert image_summary(page)[0]["title"] == "編集中に変えたタイトル"
    assert "同期しています" in page.inner_text("#codeSyncStatus")
    assert status_kind(page) == "ok"


def test_ctrl_enter_runs_code(app):
    page = app
    enter_edit_mode(page)
    page.fill("#customPyCode", code_text(page).replace(TITLE, "ショートカット"))
    run_edited_code(page, "key")
    assert image_summary(page)[0]["title"] == "ショートカット"


def test_error_shows_line_numbered_traceback(app):
    page = app
    enter_edit_mode(page)
    lines = code_text(page).split("\n")
    lines.insert(10, "undefined_name_xyz")  # 11 行目
    page.fill("#customPyCode", "\n".join(lines))
    gen = image_generation(page)
    page.click("#applyCustomCodeBtn")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    wait_run_finished(page)
    assert code_output_kind(page) == "error"
    out = code_output(page)
    assert "line 11" in out and "undefined_name_xyz" in out and "NameError" in out
    assert status_kind(page) == "error"
    assert "11行目" in status_text(page)
    assert page.inner_text("#statusDetail").strip() != ""
    assert image_generation(page) == gen  # 前の画像は残る
    assert code_text(page).split("\n")[10] == "undefined_name_xyz"  # コードは書き換えられない

    # 直して再実行すると、出力欄はエラー表示でなくなる
    lines.pop(10)
    page.fill("#customPyCode", "\n".join(lines))
    run_edited_code(page, "button")
    assert code_output_kind(page) == "ok" and "NameError" not in code_output(page)


def test_print_output_is_shown(app):
    page = app
    enter_edit_mode(page)
    page.fill("#customPyCode", 'print("hello from script")\n' + code_text(page))
    run_edited_code(page, "button")
    assert "hello from script" in code_output(page)
    assert code_output_kind(page) == "ok"


def test_save_in_edit_mode_uses_edited_code(app):
    page = app
    enter_edit_mode(page)
    code = code_text(page).replace(TITLE, "保存される編集後タイトル")
    code = code.replace('plt.rcParams["axes.unicode_minus"] = False', 'plt.rcParams["axes.unicode_minus"] = False\nplt.rcParams["svg.fonttype"] = "none"  # 文字をテキストのまま残す', 1)
    page.fill("#customPyCode", code)
    page.select_option("#saveFormat", "svg")
    download = save_plot(page)
    assert download.suggested_filename == "plot.svg"
    svg = open(download.path(), encoding="utf-8").read()
    assert "保存される編集後タイトル" in svg and TITLE not in svg
    assert status_kind(page) == "ok"


def test_no_horizontal_scroll_on_narrow_screens(page, app_url, console_log):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(app_url)
    for tab in ("tabPlotBtn", "tabDataBtn", "tabCodeBtn"):
        page.click(f"#{tab}")
        assert page.evaluate("document.documentElement.scrollWidth") <= 375, tab
