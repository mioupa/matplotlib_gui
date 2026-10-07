import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from server import start_server  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"


@pytest.fixture(scope="session")
def app_url():
    """E2E_SERVE_DIR（既定: リポジトリルート）を配信するローカルサーバーのURL。"""
    root = Path(os.environ.get("E2E_SERVE_DIR") or REPO)
    srv, url = start_server(root)
    yield url
    srv.shutdown()


@pytest.fixture(scope="session")
def base_url(app_url):
    return app_url


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES


@pytest.fixture
def page(page):
    # Pyodide起動と日本語フォント取得は遅いので、タイムアウトを長めにする
    page.set_default_timeout(180_000)
    page.set_default_navigation_timeout(180_000)
    return page


@pytest.fixture
def console_log(page, request):
    """console error / pageerror を収集し、テスト終了時にまとめて出力する。"""
    from helpers import ConsoleCollector

    c = ConsoleCollector(page)
    yield c
    c.report()
