"""openpyxl / et_xmlfile は起動時に取得せず、.xlsx を初めて読み込むときに1回だけ導入する。"""
import pytest

from helpers import load_fixture, status_kind, wait_app_ready, wait_data_ready, wait_settled

pytestmark = pytest.mark.e2e

FONT_GLOB = "**/NotoSansCJKjp-Regular.otf"
EXCEL_MARKERS = ("openpyxl", "et_xmlfile")


def _excel_requests(urls):
    return [u for u in urls if any(m in u for m in EXCEL_MARKERS) or "pypi.org" in u]


def _track(page):
    urls = []
    page.on("request", lambda r: urls.append(r.url))
    page.route(FONT_GLOB, lambda route: route.abort())  # フォントは本テストの対象外
    return urls


def test_startup_does_not_fetch_excel_wheels(page, app_url, console_log):
    urls = _track(page)
    page.goto(app_url)
    wait_app_ready(page)
    assert _excel_requests(urls) == []


def test_xlsx_installs_once_then_loads(page, app_url, fixtures_dir, console_log):
    urls = _track(page)
    page.goto(app_url)
    wait_app_ready(page)

    load_fixture(page, fixtures_dir / "multi_sheet.xlsx")
    wait_settled(page)
    first = _excel_requests(urls)
    assert len([u for u in first if "openpyxl" in u and u.endswith(".whl")]) == 1
    assert len([u for u in first if "et_xmlfile" in u and u.endswith(".whl")]) == 1
    assert all(u.startswith("https://files.pythonhosted.org/") for u in first), first
    assert "Excel" in page.inner_text("#encodingLabel")

    # 2回目の .xlsx 読込では取得しない
    page.set_input_files("#fileInput", str(fixtures_dir / "multi_sheet.xlsx"))
    page.wait_for_function("document.documentElement.dataset.loadCount === '2'")
    wait_settled(page)
    assert _excel_requests(urls) == first


def test_xlsx_install_failure_shows_japanese_error_and_csv_still_works(page, app_url, fixtures_dir, console_log):
    _track(page)
    page.route("**/files.pythonhosted.org/**", lambda route: route.abort())
    page.goto(app_url)
    wait_app_ready(page)

    page.set_input_files("#fileInput", str(fixtures_dir / "multi_sheet.xlsx"))
    page.wait_for_function("document.documentElement.dataset.dataState === 'error'")
    assert status_kind(page) == "error"
    text = page.inner_text("#status")
    assert "ネットワーク" in text and "CSV" in text

    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
