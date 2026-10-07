import pytest

from helpers import load_fixture, plot_src, save_plot, set_title, wait_app_ready, wait_plot_changed

pytestmark = pytest.mark.e2e


def test_smoke(page, app_url, fixtures_dir, console_log, tmp_path):
    page.goto(app_url)
    wait_app_ready(page)

    console_log.mark("load")
    load_fixture(page, fixtures_dir / "utf8.csv")
    first = wait_plot_changed(page, "")
    assert first.startswith("data:image/png;base64,")

    console_log.mark("rerender")
    set_title(page, "テストタイトル")
    second = wait_plot_changed(page, first)
    assert second != first
    assert plot_src(page) == second

    console_log.mark("save")
    dl = save_plot(page)
    path = tmp_path / dl.suggested_filename
    dl.save_as(path)
    data = path.read_bytes()
    assert len(data) > 0
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert dl.suggested_filename.endswith(".png")
