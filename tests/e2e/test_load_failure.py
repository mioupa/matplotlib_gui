"""スクリプトの読み込み失敗（ネットワークエラー）を利用者に知らせる。"""
import pytest

pytestmark = pytest.mark.e2e

MESSAGE = "画面の読み込みに失敗しました"


def _assert_failure_shown(page):
    page.wait_for_function("document.documentElement.dataset.appState === 'failed'", timeout=60_000)
    assert MESSAGE in page.inner_text("#status")
    assert page.get_attribute("#status", "data-kind") == "error"
    assert MESSAGE in page.inner_text("#progress")
    assert page.is_visible("#progress")


def test_failed_js_module_is_reported(page, app_url):
    page.route("**/js/ui/tabs.js", lambda route: route.abort())
    page.goto(app_url)
    _assert_failure_shown(page)


def test_failed_pyscript_core_is_reported(page, app_url):
    page.route("**/pyscript.net/releases/**/core.js", lambda route: route.abort())
    page.goto(app_url)
    _assert_failure_shown(page)
    # main.js 側は動いていても、案内が「読み込み中」で上書きされない
    assert "Python 実行環境を読み込み中" not in page.inner_text("#progress")
