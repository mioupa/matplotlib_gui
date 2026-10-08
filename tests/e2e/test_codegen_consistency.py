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
    add_files,
    add_series_with_source,
    image_summary,
    load_fixture,
    open_code_tab,
    paste_text,
    wait_data_ready,
    wait_app_ready,
    wait_code_contains,
    wait_code_generated,
    wait_latin_state,
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


def _configure_scatter_arimo_paper2_pdf(page):
    _configure_scatter(page)
    page.select_option("#latinFont", "arimo")
    wait_latin_state(page, "ready")
    page.select_option("#stylePreset", "paper2")
    page.click("#applyPresetBtn")  # cm の図サイズ
    page.select_option("#saveFormat", "pdf")


def _pre_preamble(page):
    page.fill("#skipLines", "3")  # ファイルを選ぶ前に設定する（先頭の説明の行を読み飛ばす）


def _pre_european(page):
    page.fill("#delimiter", ";")
    page.select_option("#thousands", ".")
    page.select_option("#decimal", ",")


def _configure_xy_1(page):
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")


def _configure_datetime_line(page):
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__3")


def _configure_xlsx_datetime(page):
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")


def _configure_second_sheet(page):
    page.select_option("#sheetSelect", "二枚目")
    page.wait_for_function("document.documentElement.dataset.loadCount === '2'")
    wait_settled(page)
    _configure_xy_1(page)


def _configure_two_csv(page):
    page.select_option("#series-s1-y", "__idx__1")
    add_series_with_source(page, "d2", "__idx__2")


def _configure_csv_and_second_sheet(page):
    page.select_option("#file-d2-sheet", "二枚目")
    page.wait_for_function("document.documentElement.dataset.loadCount === '3'")
    wait_settled(page)
    page.select_option("#series-s1-y", "__idx__1")
    add_series_with_source(page, "d2", "__idx__2")


# 読込の設定を変えた場合: 生成スクリプトの読込部が、GUI の読み方と同じ図を作る
PRE_STEPS = {"preamble_csv": _pre_preamble, "european_csv": _pre_european}

PASTED_FIXTURE = "tab.txt"  # 貼り付けた表の代わりに、タブ区切りのフィクスチャの中身を貼り付ける


def _paste_fixture(page, fixtures_dir):
    text = (fixtures_dir / PASTED_FIXTURE).read_text(encoding="utf-8").replace("\n", "\r\n")  # Excel のコピーは CRLF
    paste_text(page, text)
    wait_data_ready(page)


CASES = {
    "pasted_tsv": (None, _configure_xy_1),
    "line": ("growth.csv", _configure_line),
    "scatter": ("utf8.csv", _configure_scatter),
    "bar": ("categories.csv", _configure_bar),
    "xlsx_second_sheet": ("multi_sheet.xlsx", _configure_second_sheet),
    "datetime_axis": ("datetime.csv", _configure_datetime_line),
    "xlsx_datetime": ("datetime.xlsx", _configure_xlsx_datetime),
    "two_csv_files": (("utf8.csv", "growth.csv"), _configure_two_csv),
    "csv_and_xlsx_second_sheet": (("utf8.csv", "multi_sheet.xlsx"), _configure_csv_and_second_sheet),
    "preamble_csv": ("preamble.csv", _configure_xy_1),
    "european_csv": ("european.csv", _configure_xy_1),
    "scatter_paper1": ("utf8.csv", _configure_scatter_paper1),
    "scatter_arimo_paper2_pdf": ("utf8.csv", _configure_scatter_arimo_paper2_pdf),
}


def _run_in_cpython(script: Path, workdir: Path) -> tuple[list[dict], str]:
    """生成スクリプトを CPython で実行し、図の要約と標準エラー出力を返す。"""
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONPATH=str(REPO / "py"))
    proc = subprocess.run(
        [sys.executable, str(HELPER), str(script)], cwd=workdir, env=env, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("FIGURE_SUMMARY:"))
    return json.loads(line[len("FIGURE_SUMMARY:"):]), proc.stderr


EXACT_KEYS = ("title", "xlabel", "ylabel", "xscale", "yscale", "lines", "collections", "patches", "legend")


@pytest.mark.parametrize("case", list(CASES))
def test_downloaded_script_matches_browser_figure(case, page, app_url, fixtures_dir, tmp_path, console_log):
    fixture, configure = CASES[case]
    page.goto(app_url)
    wait_app_ready(page)
    if case in PRE_STEPS:
        PRE_STEPS[case](page)
    if fixture is None:
        _paste_fixture(page, fixtures_dir)
    else:
        names = fixture if isinstance(fixture, tuple) else (fixture,)
        load_fixture(page, fixtures_dir / names[0])
        wait_settled(page)
        for extra in names[1:]:
            add_files(page, [fixtures_dir / extra])
    wait_settled(page)
    configure(page)
    wait_settled(page)
    wait_code_generated(page)
    if case.endswith("_pdf"):
        wait_code_contains(page, 'fig.savefig("plot.pdf")')  # 保存設定の変更はコードだけを更新する
    browser = image_summary(page)
    assert browser, "data-summary が無い"

    open_code_tab(page)
    with page.expect_download() as dl:
        page.click("#downloadCodeBtn")
    script = tmp_path / dl.value.suggested_filename
    dl.value.save_as(script)
    if fixture is None:
        with page.expect_download() as pasted_dl:
            page.click("#savePastedBtn")  # 貼り付けたデータは、保存したファイルをスクリプトの隣に置く
        pasted_dl.value.save_as(tmp_path / pasted_dl.value.suggested_filename)
        assert pasted_dl.value.suggested_filename == "pasted_data.tsv"
    else:
        for name in fixture if isinstance(fixture, tuple) else (fixture,):
            shutil.copy(fixtures_dir / name, tmp_path / name)  # データは元のファイル名でスクリプトの隣に置く
    local, stderr = _run_in_cpython(script, tmp_path)

    assert len(local) == len(browser)
    assert len(browser) == (2 if case == "line" else 1)
    for b_ax, l_ax in zip(browser, local):
        for key in EXACT_KEYS:
            assert l_ax[key] == b_ax[key], key
        assert l_ax["xlim"] == pytest.approx(b_ax["xlim"], rel=1e-6)
        assert l_ax["ylim"] == pytest.approx(b_ax["ylim"], rel=1e-6)
    if case in ("two_csv_files", "csv_and_xlsx_second_sheet"):
        text = script.read_text(encoding="utf-8")
        assert browser[0]["lines"] == 2 and "DATA_FILE_1" in text and "DATA_FILE_2" in text and "df2.iloc[:, 2]" in text
        assert ('sheet_name="二枚目",' in text) == (case == "csv_and_xlsx_second_sheet")
    if case in ("xlsx_second_sheet", "preamble_csv", "european_csv"):
        assert len(browser) == 1 and browser[0]["lines"] == 1
        text = script.read_text(encoding="utf-8")
        expected = {
            "xlsx_second_sheet": 'sheet_name="二枚目",',
            "preamble_csv": "skiprows=3,",
            "european_csv": 'thousands=".",',
        }[case]
        assert expected in text
        if case == "european_csv":
            assert 'decimal=",",' in text and 'sep=";",' in text
            assert browser[0]["ylim"][1] > 1000  # 1.234,5 が数値として読めている
    if case == "pasted_tsv":
        assert len(browser) == 1 and browser[0]["lines"] == 1
        assert "# 貼り付けたデータ:" in script.read_text(encoding="utf-8")
    if case in ("datetime_axis", "xlsx_datetime"):
        assert "Date" in browser[0]["xconverter"] and local[0]["xconverter"] == browser[0]["xconverter"]
        assert local[0]["xticklabels"] == browser[0]["xticklabels"] and any(browser[0]["xticklabels"])
        assert ("to_datetime" in script.read_text(encoding="utf-8")) == (case == "datetime_axis")
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
    if case == "scatter_arimo_paper2_pdf":
        text = script.read_text(encoding="utf-8")
        assert '"Arimo"' in text and "17.0 / CM_PER_INCH" in text and 'plt.rcParams["pdf.fonttype"] = 42' in text
        assert "findfont" not in stderr  # Arimo が無い環境でも、警告を出さずに代わりのフォントで動く
        assert (tmp_path / "plot.pdf").read_bytes().startswith(b"%PDF")
