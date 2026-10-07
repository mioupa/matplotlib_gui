"""A6: 日本語フォントの取得（失敗時の警告は1回・再試行なし、Cache Storage からの再利用）。"""
import pytest

from helpers import (
    load_fixture,
    plot_src,
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
    page.goto(app_url)
    wait_app_ready(page)
    wait_font_done(page)
    assert page.evaluate("document.documentElement.dataset.fontState") == "ready"
    assert len(requests) == 1
    assert page.evaluate("caches.open('mplgui-fonts-v1').then(c => c.keys()).then(k => k.length)") == 1

    page.reload()
    wait_app_ready(page)
    wait_font_done(page)
    assert page.evaluate("document.documentElement.dataset.fontState") == "ready"
    assert len(requests) == 1  # 2回目はネットワークに出ない
