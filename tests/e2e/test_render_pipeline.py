"""A3（描画の合体・世代）、A4（起動中の操作の保持）、B5（進捗・描画中表示）。"""
import time

import pytest

from helpers import (
    image_generation,
    load_fixture,
    plot_src,
    render_generation,
    status_kind,
    status_text,
    wait_app_ready,
    wait_data_ready,
    wait_settled,
)

pytestmark = pytest.mark.e2e

FINAL_TITLE = "最終タイトル"


def _reference_image(page, app_url, fixture, apply):
    """リロードして、同じ最終設定を1段ずつ待ちながら作った画像（Agg の出力は決定的）。"""
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixture)
    wait_settled(page)
    apply(page)
    wait_settled(page)
    return plot_src(page)


def test_rapid_changes_coalesce_and_final_image_matches_final_settings(page, app_url, fixtures_dir, console_log):
    fixture = fixtures_dir / "utf8.csv"
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixture)
    wait_settled(page)
    first_src = plot_src(page)
    page.evaluate(
        """() => {
          window.__busy = [];
          new MutationObserver(() => window.__busy.push(document.getElementById('plotPanel').getAttribute('aria-busy')))
            .observe(document.getElementById('plotPanel'), { attributes: true, attributeFilter: ['aria-busy'] });
        }"""
    )

    # 待たずに5回、続けて間隔をあけて5回（描画の最中にも変更が入る）
    page.evaluate(
        """async (finalTitle) => {
          const el = document.getElementById('title');
          const set = (v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); };
          for (let i = 1; i <= 5; i++) set('T' + i);
          for (let i = 1; i <= 4; i++) { set('S' + i); await new Promise((r) => setTimeout(r, 280)); }
          set(finalTitle);
        }""",
        FINAL_TITLE,
    )
    wait_settled(page)
    assert status_kind(page) == "ok", status_text(page)
    assert image_generation(page) == render_generation(page)  # 表示中の画像は最新の要求のもの
    final_src = plot_src(page)
    assert final_src != first_src
    busy = page.evaluate("window.__busy")
    assert "true" in busy and busy[-1] == "false"  # aria-busy が描画中に立ち、終わると戻る

    ref = _reference_image(page, app_url, fixture, lambda p: p.fill("#title", FINAL_TITLE))
    assert ref == final_src


def test_actions_during_startup_are_kept_and_applied_once(page, app_url, fixtures_dir, console_log):
    fixture = fixtures_dir / "utf8.csv"
    held = []
    page.route("**/pyscript.toml", lambda route: held.append(route))  # Python の起動を保留する
    page.goto(app_url)
    assert page.evaluate("document.documentElement.dataset.appState") == "starting"
    assert "Python 実行環境を読み込み中" in page.inner_text("#progress")

    page.set_input_files("#fileInput", str(fixture))
    page.select_option("#plotType", "scatter")
    page.fill("#title", "起動中に入力")
    page.wait_for_timeout(600)  # デバウンスが切れても、起動前は何も走らない
    assert page.evaluate("document.documentElement.dataset.dataState") == "loading"
    assert "utf8.csv" in page.inner_text("#fileNameLabel")
    assert plot_src(page) == ""

    deadline = time.time() + 30
    while not held and time.time() < deadline:
        page.wait_for_timeout(100)
    assert held, "pyscript.toml の要求が来ていない"
    for route in held:
        route.continue_()

    wait_app_ready(page)
    page.unroute("**/pyscript.toml")
    wait_data_ready(page)
    wait_settled(page)
    assert status_kind(page) == "ok", status_text(page)
    assert render_generation(page) == "1" and image_generation(page) == "1"  # 起動後の描画は1回だけ
    assert page.eval_on_selector("#series-s1-marker-size", "e => e.value") == "24"  # scatter が反映されている
    src = plot_src(page)

    def apply(p):
        p.select_option("#plotType", "scatter")
        wait_settled(p)
        p.fill("#title", "起動中に入力")

    assert _reference_image(page, app_url, fixture, apply) == src


def test_progress_banner_hides_after_startup(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    page.wait_for_function("['ready','failed'].includes(document.documentElement.dataset.fontState)")
    page.wait_for_function("document.getElementById('progress').hidden")
