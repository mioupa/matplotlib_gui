"""軸・目盛セクションの数式（mathtext）の案内（C6）と、数式の誤りの日本語エラー。"""
import pytest

from helpers import image_generation, load_fixture, status_kind, status_text, wait_app_ready, wait_settled

pytestmark = pytest.mark.e2e

MATHTEXT_URL = "https://matplotlib.org/3.10.8/users/explain/text/mathtext.html"


def test_mathtext_help_and_errors(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    help_box = page.locator("#mathtextHelp")
    assert help_box.is_visible()
    assert "$ で囲んだ部分が数式になります" in help_box.inner_text()
    link = help_box.locator("a")
    assert link.get_attribute("href") == MATHTEXT_URL
    assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")

    page.fill("#title", "$\\alpah$")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "数式" in status_text(page)

    previous = image_generation(page)
    page.fill("#title", "m$^2$")
    page.wait_for_function("document.getElementById('status').dataset.kind !== 'error'")
    wait_settled(page)
    assert status_kind(page) != "error"
    assert image_generation(page) != previous
