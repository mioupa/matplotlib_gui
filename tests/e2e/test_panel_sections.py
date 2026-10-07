import pytest

from helpers import load_fixture, plot_src, wait_app_ready, wait_plot_changed

pytestmark = pytest.mark.e2e

SECTIONS = [
    ("sectionLoad", "データ読み込み"),
    ("sectionSeries", "系列"),
    ("sectionAxes", "軸・目盛"),
    ("sectionStyle", "体裁"),
    ("sectionSave", "保存"),
]


def is_open(page, section_id):
    return page.evaluate("(id) => document.getElementById(id).open", section_id)


def toggle(page, section_id):
    page.click(f"#{section_id} > summary")


def test_sections_order_titles_and_default_open(page, app_url):
    page.goto(app_url)
    wait_app_ready(page)
    found = page.evaluate(
        """() => Array.from(document.querySelectorAll('aside.panel > details.panel-section'))
            .map(d => [d.id, d.querySelector(':scope > summary').textContent.trim(), d.open])"""
    )
    assert [(i, t) for i, t, _ in found] == SECTIONS
    assert all(o for _, _, o in found)
    # status はセクションの外にある
    assert page.evaluate("!document.querySelector('details.panel-section #status')")


def test_close_and_reopen_hides_controls(page, app_url):
    page.goto(app_url)
    wait_app_ready(page)
    assert page.is_visible("#fontSize")
    toggle(page, "sectionStyle")
    assert not is_open(page, "sectionStyle")
    assert not page.is_visible("#fontSize")
    assert page.is_visible("#title")  # 他のセクションは開いたまま
    toggle(page, "sectionStyle")
    assert page.is_visible("#fontSize")


def test_status_stays_visible_when_sections_closed(page, app_url):
    page.goto(app_url)
    wait_app_ready(page)
    page.set_viewport_size({"width": 1280, "height": 1600})
    for section_id, _ in SECTIONS:
        toggle(page, section_id)
    # status は空でも、セクションの外にあるので閉じても隠れない（空文字の要素は高さ 0 でも display は none でない）
    assert page.evaluate("getComputedStyle(document.getElementById('status')).display") != "none"
    assert page.evaluate("document.getElementById('status').offsetParent !== null")


def test_state_persists_across_reload(page, app_url):
    page.goto(app_url)
    wait_app_ready(page)
    toggle(page, "sectionAxes")
    assert not is_open(page, "sectionAxes")
    # toggle イベントは非同期なので、保存されるのを待ってから再読み込みする
    page.wait_for_function(
        "() => (JSON.parse(localStorage.getItem('mplgui.panelSections') || '{}')).sectionAxes === false"
    )
    page.reload()
    wait_app_ready(page)
    for section_id, _ in SECTIONS:
        assert is_open(page, section_id) == (section_id != "sectionAxes")


def test_works_when_local_storage_throws(page, app_url, console_log):
    page.add_init_script(
        """
        Storage.prototype.getItem = function () { throw new Error('blocked'); };
        Storage.prototype.setItem = function () { throw new Error('blocked'); };
        """
    )
    page.goto(app_url)
    wait_app_ready(page)
    toggle(page, "sectionSave")
    assert not is_open(page, "sectionSave")
    assert not page.is_visible("#saveFilename")
    toggle(page, "sectionSave")
    assert page.is_visible("#saveFilename")
    assert [e for e in console_log.events if "blocked" in e[3]] == []


def test_render_after_toggling_sections(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    toggle(page, "sectionStyle")
    toggle(page, "sectionSave")
    load_fixture(page, fixtures_dir / "utf8.csv")
    first = wait_plot_changed(page, "")
    assert first.startswith("data:image/png;base64,")
    toggle(page, "sectionStyle")
    assert plot_src(page) == first
    assert page.is_visible("#fontSize")
