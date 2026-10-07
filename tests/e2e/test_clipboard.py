"""C5: プレビュー中の図を、保存 DPI の PNG としてクリップボードにコピーする。"""
import pytest

from helpers import (
    copy_state,
    enter_edit_mode,
    load_fixture,
    read_clipboard_png_size,
    set_save_dpi,
    status_kind,
    status_text,
    wait_app_ready,
    wait_copy_state,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def _grant(page):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])


def test_copy_png_at_save_dpi(page, app_url, fixtures_dir, console_log):
    _grant(page)
    page.goto(app_url)
    wait_app_ready(page)
    assert copy_state(page) == "idle"
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    page.click("#copyPlotBtn")
    wait_copy_state(page, "done")
    assert read_clipboard_png_size(page) == (2400, 1800)
    assert status_kind(page) == "ok"
    assert "図をクリップボードにコピーしました（PNG、300 dpi、2400 × 1800 ピクセル）。" in status_text(page)

    set_save_dpi(page, 150)
    page.select_option("#saveFormat", "pdf")  # 保存形式にかかわらず PNG をコピーする
    page.click("#copyPlotBtn")
    wait_copy_state(page, "done")
    assert read_clipboard_png_size(page) == (1200, 900)
    assert "150 dpi、1200 × 900" in status_text(page)


def test_copy_in_edit_mode_uses_the_edited_code(page, app_url, console_log):
    _grant(page)
    page.goto(app_url)
    wait_app_ready(page)
    enter_edit_mode(page)
    page.fill(
        "#customPyCode",
        "import matplotlib.pyplot as plt\nfig, ax = plt.subplots(figsize=(4, 3))\nax.plot([1, 2, 3])\n",
    )
    page.click("#copyPlotBtn")
    wait_copy_state(page, "done")
    assert read_clipboard_png_size(page) == (1200, 900)


def test_copy_without_data_shows_the_python_error(page, app_url, console_log):
    _grant(page)
    page.goto(app_url)
    wait_app_ready(page)
    page.click("#copyPlotBtn")
    wait_copy_state(page, "failed")
    assert status_kind(page) == "error" and "ファイルを読み込んで" in status_text(page)


def test_copy_unsupported_browser_warns(page, app_url, console_log):
    page.add_init_script("delete window.ClipboardItem;")
    page.goto(app_url)
    wait_app_ready(page)
    page.click("#copyPlotBtn")
    assert copy_state(page) == "unsupported"
    assert status_kind(page) == "warning"
    assert "このブラウザでは図をクリップボードにコピーできません。「保存する」で PNG を保存してください。" in status_text(page)
