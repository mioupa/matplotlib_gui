"""保存セクション: DPI（C1）、SVG の文字（C2）、PDF（Type 42）、保存設定の変更に追従するコード。"""
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from helpers import (
    code_generation,
    code_text,
    enter_edit_mode,
    image_generation,
    image_size,
    load_fixture,
    open_code_tab,
    render_generation,
    save_bytes,
    save_plot,
    set_save_dpi,
    set_title,
    status_kind,
    status_text,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_font_done,
    wait_plot_changed,
    wait_settled,
    plot_src,
)

pytestmark = pytest.mark.e2e


def _ready(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)


def test_save_dpi_sizes_and_error(page, app_url, fixtures_dir, console_log):
    _ready(page, app_url, fixtures_dir)
    assert page.input_value("#saveDpi") == "300" and not page.is_visible("#saveDpiCustom")
    assert image_size(save_bytes(page)) == (2400, 1800)  # 8 × 6 inch、300 dpi
    set_save_dpi(page, 150)
    assert image_size(save_bytes(page)) == (1200, 900)
    set_save_dpi(page, 120)  # 任意
    assert page.is_visible("#saveDpiCustom") and page.input_value("#saveDpi") == "custom"
    assert image_size(save_bytes(page)) == (960, 720)
    page.select_option("#saveFormat", "jpg")
    set_save_dpi(page, 72)
    assert not page.is_visible("#saveDpiCustom")
    assert image_size(save_bytes(page)) == (576, 432)

    set_save_dpi(page, 2000)
    page.click("#savePlotBtn")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "保存 DPI" in status_text(page)
    with pytest.raises(PlaywrightTimeout):
        with page.expect_download(timeout=2000):
            page.click("#savePlotBtn")


def test_code_follows_save_settings_without_rerender(page, app_url, fixtures_dir, console_log):
    _ready(page, app_url, fixtures_dir)
    wait_code_generated(page)
    open_code_tab(page)
    img_gen = image_generation(page)
    render_gen = render_generation(page)
    src = plot_src(page)
    assert 'fig.savefig("plot.png", dpi=300)' in code_text(page)

    page.select_option("#saveFormat", "pdf")
    wait_code_contains(page, 'plt.rcParams["pdf.fonttype"] = 42')
    assert 'fig.savefig("plot.pdf")' in code_text(page)
    assert image_generation(page) == img_gen and code_generation(page) == img_gen
    assert render_generation(page) == render_gen and plot_src(page) == src

    page.select_option("#saveFormat", "png")
    set_save_dpi(page, 600)
    wait_code_contains(page, "dpi=600")
    assert image_generation(page) == img_gen and code_generation(page) == img_gen
    assert render_generation(page) == render_gen

    # 不正な値はエラー（図とコードは前のまま）。直すとステータスが戻る
    set_save_dpi(page, 2000)
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "保存 DPI" in status_text(page)
    assert "dpi=600" in code_text(page)
    set_save_dpi(page, 150)
    wait_code_contains(page, "dpi=150")
    assert status_kind(page) == "ok" and "描画に成功しました" in status_text(page)
    assert render_generation(page) == render_gen

    # 編集モードではコードに触れない（A8）
    enter_edit_mode(page)
    before = code_text(page)
    page.select_option("#saveFormat", "svg")
    set_save_dpi(page, 72)
    page.wait_for_timeout(1000)
    assert code_text(page) == before


def test_svg_text_option_and_pdf_help(page, app_url, fixtures_dir, console_log):
    _ready(page, app_url, fixtures_dir)
    set_title(page, "Title")
    wait_settled(page)
    assert not page.is_visible("#svgTextGroup") and not page.is_visible("#pdfHelp")
    page.select_option("#saveFormat", "svg")
    assert page.is_visible("#svgTextGroup") and not page.is_visible("#pdfHelp")
    assert page.input_value("#svgText") == "path"
    assert b"<text" not in save_bytes(page)
    page.select_option("#svgText", "text")
    assert b"<text" in save_bytes(page)
    page.select_option("#saveFormat", "pdf")
    assert not page.is_visible("#svgTextGroup") and page.is_visible("#pdfHelp")
    assert "Type 42" in page.inner_text("#pdfHelp")
    # 背景透過のときは png / svg だけ。svg / pdf だけの項目は実効の形式に従う
    page.check("#saveTransparent")
    assert page.input_value("#saveFormat") == "png"
    assert not page.is_visible("#svgTextGroup") and not page.is_visible("#pdfHelp")
    page.select_option("#saveFormat", "svg")
    assert page.is_visible("#svgTextGroup")


def test_pdf_embeds_truetype_japanese_font(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    wait_font_done(page)  # 実際の Noto Sans JP（jsDelivr）の取得
    assert page.evaluate("document.documentElement.dataset.fontState") == "ready"
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    src = plot_src(page)
    set_title(page, "日本語のタイトル")
    wait_plot_changed(page, src)
    wait_settled(page)
    page.select_option("#saveFormat", "pdf")
    data = save_bytes(page)
    assert data.startswith(b"%PDF")
    assert b"/FontFile2" in data and b"NotoSansJP" in data and b"/Type3" not in data
