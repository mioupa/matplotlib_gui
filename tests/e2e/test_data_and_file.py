"""A1（データ確認の行番号と除外行）と A2（ファイル入力のリセット・ファイル名/文字コード表示）。"""
import pytest

from helpers import load_count, load_fixture, wait_app_ready, wait_load_count, wait_settled

pytestmark = pytest.mark.e2e


def _make_csv(path, rows=150):
    path.write_text("a,b\n" + "".join(f"{i},{i * 2}\n" for i in range(rows)), encoding="utf-8")
    return path


def _skipped_flags(page):
    return page.eval_on_selector_all("#dataArea tbody tr", "rows => rows.map(r => r.classList.contains('skipped-row'))")


def test_data_preview_row_numbers_and_skipped_rows(page, app_url, tmp_path, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, _make_csv(tmp_path / "many.csv"))
    wait_settled(page)
    page.click("#tabDataBtn")

    assert page.eval_on_selector("#dataArea thead th:first-child", "e => e.textContent") == "#"
    nums = page.eval_on_selector_all("#dataArea tbody tr td:first-child", "els => els.map(e => e.textContent)")
    assert nums == [str(i) for i in range(1, 101)]  # 先頭100行、ヘッダは数えない
    assert not any(_skipped_flags(page))

    loads = load_count(page)
    page.fill("#skipRows", "3")
    page.wait_for_function("document.querySelectorAll('#dataArea tbody tr.skipped-row').length === 3")
    flags = _skipped_flags(page)
    assert flags[:3] == [True] * 3 and not any(flags[3:])
    # 灰色で表示される（通常行と背景色が違う）
    bg = page.eval_on_selector_all("#dataArea tbody tr td:nth-child(2)", "els => [els[0], els[5]].map(e => getComputedStyle(e).backgroundColor)")
    assert bg[0] != bg[1]

    page.fill("#skipRows", "1")
    page.wait_for_function("document.querySelectorAll('#dataArea tbody tr.skipped-row').length === 1")
    page.fill("#skipRows", "")
    page.wait_for_function("document.querySelectorAll('#dataArea tbody tr.skipped-row').length === 0")
    assert load_count(page) == loads  # ファイルは再読込していない
    # 再読込（ヘッダ設定変更）後も skipRows が反映される
    page.fill("#skipRows", "2")
    wait_settled(page)
    page.uncheck("#hasHeader")
    wait_load_count(page, loads + 1)
    page.wait_for_function("document.querySelectorAll('#dataArea tbody tr.skipped-row').length === 2")


def test_file_picker_shows_selected_name(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    assert "選択されていません" in page.inner_text("#fileNameLabel")
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    text = page.inner_text("#fileNameLabel")
    assert "utf8.csv" in text
    assert "選択されていません" not in text
    assert page.eval_on_selector("#fileInput", "e => e.value") == ""


def test_file_input_reset_and_labels(page, app_url, fixtures_dir, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    src = fixtures_dir / "utf8.csv"
    load_fixture(page, src)
    wait_settled(page)
    assert page.eval_on_selector("#fileInput", "e => e.value") == ""
    assert "utf8.csv" in page.inner_text("#fileNameLabel")
    assert "UTF-8" in page.inner_text("#encodingLabel")
    assert load_count(page) == 1

    # 同じファイルをもう一度選ぶと再読込される
    page.set_input_files("#fileInput", str(src))
    wait_load_count(page, 2)
    wait_settled(page)
    assert page.eval_on_selector("#fileInput", "e => e.value") == ""

    # 区切り文字・ヘッダの変更でも、保持している File で再読込できる
    page.uncheck("#hasHeader")
    wait_load_count(page, 3)
    wait_settled(page)

    page.set_input_files("#fileInput", str(fixtures_dir / "multi_sheet.xlsx"))
    wait_load_count(page, 4)
    assert "Excel" in page.inner_text("#encodingLabel")
