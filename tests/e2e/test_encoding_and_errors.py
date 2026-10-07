"""A5（文字コード判定と表示）、A7（数値にできない値の警告）、B7（日本語エラーと復帰）。"""
import pytest

from helpers import (
    load_fixture,
    plot_src,
    status_kind,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_plot_changed,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def _open(page, app_url, fixtures_dir, name):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / name)
    wait_settled(page)


def _header_cells(page):
    page.click("#tabDataBtn")
    return page.eval_on_selector_all("#dataArea thead th", "els => els.map(e => e.textContent)")


def test_cp932_is_detected_and_machine_dependent_characters_survive(page, app_url, fixtures_dir, console_log):
    _open(page, app_url, fixtures_dir, "cp932.csv")
    assert "Shift_JIS（CP932）" in page.inner_text("#encodingLabel")
    assert "時間①" in _header_cells(page)
    assert "㈱テスト" in page.inner_text("#dataArea")


def test_utf8_bom_is_labelled_and_not_in_header(page, app_url, fixtures_dir, console_log):
    _open(page, app_url, fixtures_dir, "utf8_bom.csv")
    assert "UTF-8（BOM付き）" in page.inner_text("#encodingLabel")
    headers = _header_cells(page)
    assert headers[1] == "時間" and "﻿" not in "".join(headers)


def test_euc_jp_is_detected(page, app_url, fixtures_dir, console_log):
    _open(page, app_url, fixtures_dir, "euc_jp.csv")
    assert "EUC-JP" in page.inner_text("#encodingLabel")
    assert "測定開始" in _header_cells(page)[-1] + page.inner_text("#dataArea")


def test_undecodable_file_shows_japanese_error(page, app_url, tmp_path, console_log):
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"a,b\n\xff\xff\xff\xff\n")
    page.goto(app_url)
    wait_app_ready(page)
    page.set_input_files("#fileInput", str(bad))
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    assert "文字コードを判定できませんでした" in status_text(page) and "UTF-8 で保存し直して" in status_text(page)


def test_non_numeric_values_produce_warning_and_plot_still_renders(page, app_url, fixtures_dir, console_log):
    _open(page, app_url, fixtures_dir, "non_numeric.csv")
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__1")  # 金額: "1,234" 形式は数値に変換できない
    wait_settled(page)
    page.wait_for_function("document.getElementById('status').dataset.kind === 'warning'")
    wait_settled(page)
    assert status_kind(page) == "warning"
    warnings = status_warnings(page)
    assert len(warnings) == 1
    w = warnings[0]
    assert "系列2（金額）" in w and "数値に変換できない値が20件あったため、その行を除外しました" in w and '"1,234"' in w
    assert plot_src(page) != "" and plot_src(page).startswith("data:image/png")


def test_invalid_setting_error_names_field_and_recovers(page, app_url, fixtures_dir, console_log):
    _open(page, app_url, fixtures_dir, "utf8.csv")
    src = plot_src(page)
    page.fill("#xMin", "5")
    page.fill("#xMax", "1")
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'")
    wait_settled(page)
    assert "X軸の範囲" in status_text(page) and "最小値 < 最大値" in status_text(page)
    assert plot_src(page) == src  # 直前の画像は残る
    page.fill("#xMax", "10")
    new = wait_plot_changed(page, src)
    wait_settled(page)
    assert status_kind(page) == "ok" and new != src
