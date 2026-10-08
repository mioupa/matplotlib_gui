"""C3: 欧文フォント（Arimo / Tinos）。選んだときだけ取得し、登録・描画・コード・PDF に反映する。"""
import pytest

from helpers import (
    ARIMO_GLOB,
    TINOS_GLOB,
    code_text,
    enter_edit_mode,
    image_generation,
    latin_font_state,
    load_fixture,
    open_code_tab,
    plot_src,
    render_generation,
    save_bytes,
    set_title,
    status_kind,
    status_warnings,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_latin_state,
    wait_plot_changed,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def _track(page):
    requests = []
    page.on(
        "request",
        lambda r: requests.append(r.url) if r.url.endswith(("Arimo_400Regular.ttf", "Tinos_400Regular.ttf")) else None,
    )
    return requests


def _ready(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    wait_code_generated(page)


def test_latin_fonts_are_fetched_only_when_selected(page, app_url, fixtures_dir, console_log):
    requests = _track(page)
    _ready(page, app_url, fixtures_dir)
    assert latin_font_state(page) == "idle"
    src = plot_src(page)
    set_title(page, "通常の描画")
    wait_plot_changed(page, src)
    wait_settled(page)
    assert requests == []  # 起動時にも通常の描画でも取得しない

    gen = image_generation(page)
    page.select_option("#latinFont", "arimo")
    wait_latin_state(page, "ready")
    wait_settled(page)
    assert len(requests) == 1 and requests[0].endswith("Arimo_400Regular.ttf")
    assert image_generation(page) != gen  # 描き直された
    open_code_tab(page)
    wait_code_contains(page, '"Arimo"')
    assert "latin = [name for name in" in code_text(page)
    page.select_option("#saveFormat", "pdf")
    assert b"Arimo" in save_bytes(page)

    page.select_option("#latinFont", "default")
    assert latin_font_state(page) == "idle"
    wait_settled(page)
    page.select_option("#latinFont", "arimo")  # 選び直しても取得しない
    wait_latin_state(page, "ready")
    wait_settled(page)
    assert len(requests) == 1

    page.select_option("#latinFont", "tinos")
    wait_latin_state(page, "ready")
    wait_settled(page)
    assert len(requests) == 2 and requests[1].endswith("Tinos_400Regular.ttf")
    wait_code_contains(page, '"Tinos"')
    assert "mathtext.fontset" in code_text(page) and '"stix"' in code_text(page)
    assert b"Tinos" in save_bytes(page)


def test_latin_font_failure_warns_once_and_keeps_rendering(page, app_url, fixtures_dir, console_log):
    requests = _track(page)
    page.route(ARIMO_GLOB, lambda route: route.abort())
    _ready(page, app_url, fixtures_dir)
    page.select_option("#latinFont", "arimo")
    wait_latin_state(page, "failed")
    wait_settled(page)
    assert plot_src(page).startswith("data:image/png")
    warnings = status_warnings(page)
    assert len(warnings) == 1 and "Arimo" in warnings[0] and "標準のフォント" in warnings[0]
    assert status_kind(page) == "warning"

    src = plot_src(page)
    set_title(page, "再描画")
    wait_plot_changed(page, src)
    wait_settled(page)
    assert len(status_warnings(page)) == 1  # 増えない（成功メッセージにも添えて残る）

    page.select_option("#latinFont", "default")
    wait_settled(page)
    assert status_warnings(page) == [] and latin_font_state(page) == "idle"
    page.select_option("#latinFont", "arimo")
    wait_settled(page)
    assert latin_font_state(page) == "failed" and len(status_warnings(page)) == 1
    assert len(requests) == 1  # 再試行しない


def test_latin_font_is_served_from_cache_storage_on_reload(page, app_url, console_log):
    requests = _track(page)
    page.goto(app_url)
    wait_app_ready(page)
    page.select_option("#latinFont", "arimo")
    wait_latin_state(page, "ready")
    assert len(requests) == 1
    page.reload()
    wait_app_ready(page)
    page.select_option("#latinFont", "arimo")
    wait_latin_state(page, "ready")
    assert len(requests) == 1  # 2回目はネットワークに出ない


def test_slow_latin_font_renders_with_fallback_then_rerenders_once(page, app_url, fixtures_dir, console_log):
    page.add_init_script("window.__MPLGUI_TEST_OVERRIDES__ = {fontStallMs: 60000, fontFirstRenderWaitMs: 500};")
    held = []
    page.route(ARIMO_GLOB, lambda route: held.append(route))
    _ready(page, app_url, fixtures_dir)
    page.select_option("#latinFont", "arimo")
    page.wait_for_function("document.documentElement.dataset.renderGeneration && Number(document.documentElement.dataset.renderGeneration) >= 2")
    wait_settled(page)
    assert latin_font_state(page) == "loading" and len(held) == 1
    gen = int(render_generation(page))
    img = image_generation(page)
    held[0].continue_()
    wait_latin_state(page, "ready")
    page.wait_for_function(f"Number(document.documentElement.dataset.renderGeneration) > {gen}")
    wait_settled(page)
    page.wait_for_timeout(1000)
    assert int(render_generation(page)) == gen + 1  # 追加の描画はちょうど1回
    assert image_generation(page) != img


def test_selecting_latin_font_in_edit_mode_fetches_but_does_not_render(page, app_url, fixtures_dir, console_log):
    requests = _track(page)
    _ready(page, app_url, fixtures_dir)
    enter_edit_mode(page)
    code = code_text(page)
    gen = image_generation(page)
    render_gen = render_generation(page)
    page.select_option("#latinFont", "tinos")
    wait_latin_state(page, "ready")
    page.wait_for_timeout(1000)
    assert len(requests) == 1
    assert code_text(page) == code and image_generation(page) == gen and render_generation(page) == render_gen
