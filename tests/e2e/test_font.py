"""A6: 日本語フォントの取得（失敗時の警告は1回・再試行なし、Cache Storage からの再利用）。"""
import matplotlib
import pytest
from pathlib import Path

from helpers import (
    load_fixture,
    image_generation,
    plot_src,
    render_generation,
    set_title,
    status_kind,
    status_warnings,
    wait_app_ready,
    wait_font_done,
    wait_plot_changed,
    wait_settled,
)

pytestmark = pytest.mark.e2e

FONT_GLOB = "**/NotoSansCJKjp-Regular.otf"
# 16MB の実フォントの代わりに、matplotlib 同梱の小さな TTF を CDN の代役として配信する（登録・Cache Storage の経路は本物と同じ）
STAND_IN_FONT = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"


def _overrides(page, stall_ms, first_render_wait_ms):
    page.add_init_script(
        f"window.__MPLGUI_TEST_OVERRIDES__ = {{fontStallMs: {stall_ms}, fontFirstRenderWaitMs: {first_render_wait_ms}}};"
    )


def _font_state(page):
    return page.evaluate("document.documentElement.dataset.fontState")


def test_font_failure_warns_once_and_plot_still_renders(page, app_url, fixtures_dir, console_log):
    requests = []
    page.route(FONT_GLOB, lambda route: (requests.append(route.request.url), route.abort()))
    page.goto(app_url)
    wait_app_ready(page)
    wait_font_done(page)
    assert page.evaluate("document.documentElement.dataset.fontState") == "failed"

    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    assert plot_src(page).startswith("data:image/png")
    warnings = status_warnings(page)
    assert len(warnings) == 1 and "日本語フォント" in warnings[0]
    assert status_kind(page) == "warning"

    src = plot_src(page)
    set_title(page, "再描画")
    wait_plot_changed(page, src)
    wait_settled(page)
    assert len(status_warnings(page)) == 1  # 増えない
    assert len(requests) == 1  # 再試行しない


def test_font_is_served_from_cache_storage_on_reload(page, app_url, console_log):
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("NotoSansCJKjp-Regular.otf") else None)
    page.route(
        FONT_GLOB,
        lambda route: route.fulfill(status=200, content_type="font/ttf", body=STAND_IN_FONT.read_bytes()),
    )
    page.goto(app_url)
    wait_app_ready(page)
    wait_font_done(page)
    assert _font_state(page) == "ready", "font did not become ready (stand-in font served via page.route)"
    assert len(requests) == 1
    assert page.evaluate("caches.open('mplgui-fonts-v1').then(c => c.keys()).then(k => k.length)") == 1

    page.reload()
    wait_app_ready(page)
    wait_font_done(page)
    assert _font_state(page) == "ready"
    assert len(requests) == 1  # 2回目はネットワークに出ない


def test_stalled_font_fails_once_and_plot_renders(page, app_url, fixtures_dir, console_log):
    _overrides(page, stall_ms=1000, first_render_wait_ms=500)
    requests = []
    held = []

    def handler(route):
        requests.append(route.request.url)
        held.append(route)  # 応答せずに保持する（接続が止まった状態）

    page.route(FONT_GLOB, handler)
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_font_done(page, timeout=30_000)
    assert _font_state(page) == "failed"
    wait_settled(page)
    assert plot_src(page).startswith("data:image/png")
    warnings = status_warnings(page)
    assert len(warnings) == 1 and "日本語フォント" in warnings[0]
    assert status_kind(page) == "warning"

    src = plot_src(page)
    set_title(page, "再描画")
    wait_plot_changed(page, src)
    wait_settled(page)
    page.wait_for_timeout(1500)
    assert len(status_warnings(page)) == 1
    assert len(requests) == 1  # 再試行しない


def test_slow_font_renders_with_fallback_then_rerenders_once(page, app_url, fixtures_dir, console_log):
    _overrides(page, stall_ms=60_000, first_render_wait_ms=500)
    held = []
    page.route(FONT_GLOB, lambda route: held.append(route))
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    # フォントはまだ届いていないが、待ち時間の上限で最初の図が出る
    assert _font_state(page) == "loading"
    assert plot_src(page).startswith("data:image/png")
    gen_before = int(render_generation(page))
    img_gen_before = image_generation(page)
    first_src = plot_src(page)
    assert len(held) == 1

    held[0].fulfill(status=200, content_type="font/ttf", body=STAND_IN_FONT.read_bytes())
    wait_font_done(page, timeout=60_000)
    assert _font_state(page) == "ready"
    page.wait_for_function(
        f"Number(document.documentElement.dataset.renderGeneration) > {gen_before}", timeout=60_000
    )
    wait_settled(page)
    page.wait_for_timeout(1000)
    assert int(render_generation(page)) == gen_before + 1  # 追加の描画はちょうど1回
    assert image_generation(page) != img_gen_before
    assert status_warnings(page) == []
