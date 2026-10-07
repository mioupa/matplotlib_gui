"""生成したスクリプトの一致確認（要件 7 章）: .py を CPython で実行した図と、ブラウザで描いた図の要素が一致すること。

フォントは CPython とブラウザで異なるので、画素やレイアウトは比べない。系列数・軸範囲・ラベル・凡例・スケールを比べる。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import (
    image_summary,
    load_fixture,
    open_code_tab,
    wait_app_ready,
    wait_code_generated,
    wait_settled,
)

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("run_script_summary.py")


def _configure_line(page):
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__2")
    page.check("#series-s2-use-y2")
    page.fill("#title", "指数と線形")
    page.fill("#xLabel", "時間 (s)")
    page.fill("#yLabel", "指数")
    page.fill("#y2Label", "線形")
    page.select_option("#yScale", "log")


def _configure_scatter(page):
    page.select_option("#plotType", "scatter")
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.fill("#title", "散布図")


def _configure_bar(page):
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    page.fill("#title", "品目別の売上")
    page.fill("#yLabel", "売上")


def _configure_scatter_paper1(page):
    _configure_scatter(page)
    page.select_option("#stylePreset", "paper1")
    page.click("#applyPresetBtn")  # 図のサイズ（cm）、フォント 8 pt、線幅、点サイズ 9


CASES = {
    "line": ("growth.csv", _configure_line),
    "scatter": ("utf8.csv", _configure_scatter),
    "bar": ("categories.csv", _configure_bar),
    "scatter_paper1": ("utf8.csv", _configure_scatter_paper1),
}


def _run_in_cpython(script: Path, workdir: Path) -> list[dict]:
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONPATH=str(REPO / "py"))
    proc = subprocess.run(
        [sys.executable, str(HELPER), str(script)], cwd=workdir, env=env, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("FIGURE_SUMMARY:"))
    return json.loads(line[len("FIGURE_SUMMARY:"):])


EXACT_KEYS = ("title", "xlabel", "ylabel", "xscale", "yscale", "lines", "collections", "patches", "legend")


@pytest.mark.parametrize("case", list(CASES))
def test_downloaded_script_matches_browser_figure(case, page, app_url, fixtures_dir, tmp_path, console_log):
    fixture, configure = CASES[case]
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)
    configure(page)
    wait_settled(page)
    wait_code_generated(page)
    browser = image_summary(page)
    assert browser, "data-summary が無い"

    open_code_tab(page)
    with page.expect_download() as dl:
        page.click("#downloadCodeBtn")
    script = tmp_path / dl.value.suggested_filename
    dl.value.save_as(script)
    shutil.copy(fixtures_dir / fixture, tmp_path / fixture)  # データは元のファイル名でスクリプトの隣に置く
    local = _run_in_cpython(script, tmp_path)

    assert len(local) == len(browser)
    assert len(browser) == (2 if case == "line" else 1)
    for b_ax, l_ax in zip(browser, local):
        for key in EXACT_KEYS:
            assert l_ax[key] == b_ax[key], key
        assert l_ax["xlim"] == pytest.approx(b_ax["xlim"], rel=1e-6)
        assert l_ax["ylim"] == pytest.approx(b_ax["ylim"], rel=1e-6)
    if case == "bar":
        assert local[0]["xticklabels"] == browser[0]["xticklabels"]
        assert "品目A" in browser[0]["xticklabels"][0]
        assert browser[0]["patches"] == 12  # 2 系列 × 6 カテゴリ
    if case == "line":
        assert browser[0]["yscale"] == "log" and browser[0]["lines"] == 1 and browser[1]["lines"] == 1
        assert browser[0]["legend"] == ["指数 [1]", "線形 [2]"]
    if case.startswith("scatter"):
        assert browser[0]["collections"] == 1 and browser[0]["lines"] == 0
    if case == "scatter_paper1":
        assert "8.5 / CM_PER_INCH" in script.read_text(encoding="utf-8")  # cm で指定した図サイズのまま書き出される
