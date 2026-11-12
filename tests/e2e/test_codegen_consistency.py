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
    add_annotation,
    add_fit,
    add_series_with_source,
    image_summary,
    load_fixture,
    open_code_tab,
    open_tick_group,
    paste_text,
    set_errorbars,
    set_fill,
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


def _configure_ticks_fixed_inverted(page):
    _configure_xy_1(page)
    for axis in ("x", "y"):
        open_tick_group(page, axis)
    page.select_option("#yTickFormat", "fixed")
    page.fill("#yTickDecimals", "2")
    page.check("#yInverted")
    page.uncheck("#spineTop")
    page.uncheck("#spineRight")
    page.select_option("#xMinorTicks", "on")
    page.fill("#xMinorDivisions", "4")
    page.select_option("#yMinorTicks", "on")
    page.fill("#yMinorDivisions", "5")


def _configure_ticks_pow10(page):
    _configure_xy_1(page)
    open_tick_group(page, "y")
    page.select_option("#yTickFormat", "pow10")
    page.fill("#yMajorStep", "250")


def _configure_datetime_month_range(page):
    _configure_datetime_line(page)
    open_tick_group(page, "x")
    page.select_option("#xMajorStepUnit", "day")
    page.fill("#xMajorStep", "2")
    page.fill("#xDateMin", "2026-01-01")
    page.fill("#xDateMax", "2026-01-05 12:00")


def _configure_text_x_step(page):
    page.select_option("#series-s1-x", "__idx__1")  # ID（文字列の列）
    page.select_option("#series-s1-y", "__idx__3")
    open_tick_group(page, "x")
    page.fill("#xMajorStep", "10")


def _configure_errbars_line(page):
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    set_errorbars(page, "s1", "y", mode="column", column="__idx__3")
    set_errorbars(page, "s1", "x", mode="fixed", value="0.2")


def _configure_errbars_scatter(page):
    page.select_option("#plotType", "scatter")
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    set_errorbars(page, "s1", "y", mode="column", symmetric=False, column="__idx__4", column_minus="__idx__5")


def _configure_errbars_bar(page):
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    set_errorbars(page, "s1", "y", mode="fixed", value="2.5")


def _configure_errbars_bar_multi(page):
    page.select_option("#plotType", "bar")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    set_errorbars(page, "s1", "y", mode="fixed", value="2.5")
    set_errorbars(page, "s2", "y", mode="fixed", symmetric=False, value="3", value_minus="1")


def _configure_errbars_two_files(page):
    page.select_option("#series-s1-y", "__idx__1")
    add_series_with_source(page, "d2", "__idx__1")
    set_errorbars(page, "s2", "y", mode="column", column="__idx__3")


# band.csv の列: 0 x, 1 mean, 2 lo, 3 hi, 4 day, 5 other
def _band_base(page, x="__idx__0"):
    page.select_option("#series-s1-x", x)
    page.select_option("#series-s1-y", "__idx__1")


def _configure_style_line_band(page):
    _band_base(page)
    page.select_option("#series-s1-marker", "s")
    page.fill("#series-s1-alpha", "0.8")
    set_fill(page, "s1", lower="__idx__2", upper="__idx__3", alpha=0.3)


def _configure_band_datetime_scatter(page):
    page.select_option("#plotType", "scatter")
    _band_base(page, "__idx__4")
    set_fill(page, "s1", lower="__idx__2", upper="__idx__3")


def _configure_annotations_numeric(page):
    _band_base(page)
    add_annotation(page, "hline", y="10", label="基準値", line_width="1.5")
    add_annotation(page, "vline", x="5", line_style="solid")
    add_annotation(page, "vspan", start="2", end="4", label="区間")
    add_annotation(page, "hspan", start="5", end="8", alpha="0.1")
    add_annotation(page, "text", text="ピーク $\\alpha$", x="3", y="8", font_size="14")
    add_annotation(page, "text", text="左上", coords="axes", x="0.05", y="0.95")


def _configure_annotations_datetime(page):
    _band_base(page, "__idx__4")
    add_annotation(page, "vline", x="2026-01-05 12:00", label="イベント")
    add_annotation(page, "vspan", start="2026-01-02", end="2026-01-04")
    add_annotation(page, "text", text="注目", x="2026-01-08", y="12")


def _configure_annotations_y2(page):
    _band_base(page)
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__5")
    page.check("#series-s2-use-y2")
    add_annotation(page, "hline", y="50", axis="y2", label="右の基準")
    add_annotation(page, "hspan", start="60", end="80", axis="y2")
    add_annotation(page, "hline", y="10")


def _configure_fit_linear_legend(page):
    _band_base(page)
    page.fill("#series-s1-legend-name", "温度")
    add_fit(page)


def _configure_fit_poly_text(page):
    _band_base(page)
    add_fit(page, model="poly", degree="3", show="text", line_style="solid")
    add_fit(page, model="linear", show="text")


def _configure_fit_custom(page):
    _band_base(page)
    page.fill("#series-s1-legend-name", "温度")
    add_fit(page, model="custom", expr="a*x^2 + b*x + c")


def _configure_fit_y2(page):
    _band_base(page)
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__0")
    page.select_option("#series-s2-y", "__idx__5")
    page.check("#series-s2-use-y2")
    add_fit(page, series="s2")
    add_fit(page, series="s1", show="none")


# --- グラフの種類（Phase 5c, G7）。fixture は chart_types.csv（0 category / 1 a / 2 b / 3 c / 4 err / 5 m） ---
def _configure_step(page):
    page.select_option("#plotType", "step")
    page.select_option("#stepWhere", "mid")
    page.select_option("#series-s1-x", "__idx__1")
    page.select_option("#series-s1-y", "__idx__2")


def _configure_barh_err(page):
    page.select_option("#plotType", "barh")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    set_errorbars(page, "s1", "y", mode="column", column="__idx__4")


def _configure_bar_stacked(page):
    page.select_option("#plotType", "barStacked")
    page.select_option("#xColumn", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")  # 正負が混ざる


def _configure_hist(page):
    page.select_option("#plotType", "hist")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__5")  # 数値にできない値と空欄を含む
    page.fill("#histBins", "6")
    page.check("#histDensity")


def _configure_scatter_color(page):
    page.select_option("#plotType", "scatterColor")
    page.select_option("#series-s1-x", "__idx__1")
    page.select_option("#series-s1-y", "__idx__2")
    page.select_option("#series-s1-color-column", "__idx__3")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", "__idx__1")
    page.select_option("#series-s2-y", "__idx__4")
    page.select_option("#series-s2-color-column", "__idx__3")
    page.select_option("#colorMap", "coolwarm")
    page.fill("#colorbarLabel", "電流 (A)")


def _configure_box(page):
    page.select_option("#plotType", "box")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__5")  # 数値にできない値と空欄を含む
    page.check("#boxMeans")


def _configure_violin(page):
    page.select_option("#plotType", "violin")
    page.select_option("#series-s1-y", "__idx__1")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__2")
    page.check("#violinMeans")


def _configure_heatmap(page):
    page.select_option("#plotType", "heatmap")
    page.select_option("#series-s1-x", "__idx__0")
    page.select_option("#series-s1-y", "__idx__1")
    page.select_option("#series-s1-color-column", "__idx__2")
    page.select_option("#colorMap", "coolwarm")
    page.fill("#colorbarLabel", "値")


# --- 計算した列（Phase 5c, G6） ---
def _configure_computed_one_file(page):
    page.fill("#skipRows", "2")  # 計算は、除外した行を除いて行う（max もその行だけ）
    page.click("#addComputedBtn")
    page.fill("#computed-c1-name", "正規化")
    page.fill("#computed-c1-expr", "[1] / max([1])")
    page.select_option("#series-s1-x", "__idx__2")
    page.select_option("#series-s1-y", "__idx__6")


def _configure_computed_two_files(page):
    page.click("#addComputedBtn")
    page.select_option("#computed-c1-source", "d2")
    page.fill("#computed-c1-expr", "rolling_mean([1], 3) - first([1])")
    page.select_option("#series-s1-y", "__idx__2")
    add_series_with_source(page, "d2", "__idx__6")


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
    "ticks_fixed_inverted": ("growth.csv", _configure_ticks_fixed_inverted),
    "ticks_pow10": ("growth.csv", _configure_ticks_pow10),
    "datetime_day_step_range": ("datetime.csv", _configure_datetime_month_range),
    "text_x_step": ("datetime.csv", _configure_text_x_step),
    "errbars_line": ("errorbars.csv", _configure_errbars_line),
    "errbars_scatter": ("errorbars.csv", _configure_errbars_scatter),
    "errbars_bar": ("categories.csv", _configure_errbars_bar),
    "errbars_bar_multi": ("categories.csv", _configure_errbars_bar_multi),
    "errbars_two_files": (("utf8.csv", "errorbars.csv"), _configure_errbars_two_files),
    "style_line_band": ("band.csv", _configure_style_line_band),
    "band_datetime_scatter": ("band.csv", _configure_band_datetime_scatter),
    "annotations_numeric": ("band.csv", _configure_annotations_numeric),
    "annotations_datetime": ("band.csv", _configure_annotations_datetime),
    "annotations_y2": ("band.csv", _configure_annotations_y2),
    "fit_linear_legend": ("band.csv", _configure_fit_linear_legend),
    "fit_poly_text": ("band.csv", _configure_fit_poly_text),
    "fit_custom": ("band.csv", _configure_fit_custom),
    "fit_y2": ("band.csv", _configure_fit_y2),
    "type_step": ("chart_types.csv", _configure_step),
    "type_barh_err": ("chart_types.csv", _configure_barh_err),
    "type_bar_stacked": ("chart_types.csv", _configure_bar_stacked),
    "type_hist": ("chart_types.csv", _configure_hist),
    "type_scatter_color": ("chart_types.csv", _configure_scatter_color),
    "type_box": ("chart_types.csv", _configure_box),
    "type_violin": ("chart_types.csv", _configure_violin),
    "type_heatmap": ("grid.csv", _configure_heatmap),
    "computed_one_file": ("chart_types.csv", _configure_computed_one_file),
    "computed_two_files": (("chart_types.csv", "band.csv"), _configure_computed_two_files),
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


TICK_CASES = ("ticks_fixed_inverted", "ticks_pow10", "datetime_day_step_range", "text_x_step")


def l_ax_summary(summary, key):
    return summary[0][key]


EXACT_KEYS = (
    "title", "xlabel", "ylabel", "xscale", "yscale", "lines", "collections", "patches", "legend",
    "bands", "markers", "alphas", "annotations", "fitlines", "fittexts",  # Phase 5b
    "drawstyles", "bars", "colorbar",  # Phase 5c
    "boxes", "violins", "meshes",  # Phase 5d
)


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
    assert len(browser) == (2 if case in ("line", "annotations_y2", "fit_y2") else 1)
    if case.startswith("errbars_"):
        assert browser[0]["errorbars"] > 0
        assert l_ax_summary(local, "errorbars") == l_ax_summary(browser, "errorbars")
        text = script.read_text(encoding="utf-8")
        is_bar = case in ("errbars_bar", "errbars_bar_multi")
        assert ("draw_error_bars(" in text) != is_bar  # 折れ線・散布図はヘルパー、棒グラフは ax.bar の yerr
        if is_bar:
            assert "yerr=" in text
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
    if case in TICK_CASES:
        for key in ("xinverted", "yinverted", "spines", "xmajor", "ymajor", "xminor", "yminor", "xformatter", "yformatter", "yoffset"):
            assert l_ax_summary(local, key) == l_ax_summary(browser, key), key
    if case == "ticks_fixed_inverted":
        assert browser[0]["yinverted"] and not browser[0]["xinverted"]
        assert browser[0]["spines"] == {"top": False, "right": False}
        assert browser[0]["yformatter"] == "FormatStrFormatter" and browser[0]["xminor"] == browser[0]["yminor"] == "AutoMinorLocator"
        assert local[0]["yticklabels"] == browser[0]["yticklabels"]  # 位置は MultipleLocator でなくても、書式は同じ
    if case == "ticks_pow10":
        assert browser[0]["ymajor"] == "MultipleLocator" and browser[0]["yformatter"] == "ScalarFormatter"
        assert local[0]["yticklabels"] == browser[0]["yticklabels"] and browser[0]["yoffset"]
    if case == "datetime_day_step_range":
        assert browser[0]["xmajor"] == "DayLocator" and local[0]["xlim"] == pytest.approx(browser[0]["xlim"])
        assert local[0]["xticklabels"] == browser[0]["xticklabels"]
        assert 'ax.set_xlim(left=pd.Timestamp("2026-01-01"), right=pd.Timestamp("2026-01-05 12:00:00"))' in script.read_text(encoding="utf-8")
    if case == "text_x_step":
        assert browser[0]["xmajor"] == "MultipleLocator" and local[0]["xticklabels"] == browser[0]["xticklabels"]
        assert "MultipleLocator(10)" in script.read_text(encoding="utf-8")
    if case == "bar":
        assert local[0]["xticklabels"] == browser[0]["xticklabels"]
        assert "品目A" in browser[0]["xticklabels"][0]
        assert browser[0]["patches"] == 12  # 2 系列 × 6 カテゴリ
    if case == "errbars_two_files":
        assert "df2.iloc[:, 3]" in script.read_text(encoding="utf-8")
    if case in ("errbars_bar", "errbars_bar_multi"):
        assert local[0]["xticklabels"] == browser[0]["xticklabels"]
    if case == "style_line_band":
        assert browser[0]["bands"] == 1 and browser[0]["markers"] == ["s"] and browser[0]["alphas"] == [0.8]
    if case == "band_datetime_scatter":
        assert browser[0]["bands"] == 1 and local[0]["xticklabels"] == browser[0]["xticklabels"]
    if case == "annotations_numeric":
        assert browser[0]["annotations"] == {"texts": 2, "hlines": 1, "vlines": 1, "hspans": 1, "vspans": 1}
        assert "基準値" in browser[0]["legend"] and "区間" in browser[0]["legend"]
    if case == "annotations_datetime":
        assert browser[0]["annotations"] == {"texts": 1, "hlines": 0, "vlines": 1, "hspans": 0, "vspans": 1}
        assert "pd.Timestamp(" in script.read_text(encoding="utf-8")
    if case == "annotations_y2":
        assert browser[1]["annotations"]["hlines"] == 1 and browser[1]["annotations"]["hspans"] == 1
        assert browser[0]["annotations"]["hlines"] == 1
    if case == "fit_linear_legend":
        assert browser[0]["fitlines"] == 1 and any(t.startswith("温度の近似") for t in browser[0]["legend"])
        assert "poly_text(" in script.read_text(encoding="utf-8")
    if case == "fit_poly_text":
        assert browser[0]["fitlines"] == 2 and browser[0]["fittexts"] == 2
    if case == "fit_custom":
        assert browser[0]["fitlines"] == 1 and any("a = " in t for t in browser[0]["legend"])
        assert "from scipy.optimize import curve_fit" in script.read_text(encoding="utf-8")
    if case == "fit_y2":
        assert browser[1]["fitlines"] == 1 and browser[0]["fitlines"] == 1
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
