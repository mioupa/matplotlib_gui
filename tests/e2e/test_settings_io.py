"""R1: 設定の保存・読込（JSON）、前回の設定の自動復元、初期設定に戻す。"""
import json

import pytest

from helpers import (
    add_annotation,
    add_computed,
    add_files,
    add_series_with_source,
    app_state,
    code_text,
    enter_edit_mode,
    file_row_ids,
    image_generation,
    image_summary,
    last_settings_raw,
    load_count,
    load_fixture,
    load_settings_file,
    reset_settings,
    save_settings_file,
    series_state,
    set_layout,
    set_save_dpi,
    set_series_panel,
    settings_applied,
    state_list,
    status_kind,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_code_generated,
    wait_last_settings,
    wait_last_settings_removed,
    wait_load_count,
    wait_settings_applied,
    wait_settled,
)

pytestmark = pytest.mark.e2e

X, MEAN, LO, OTHER = "__idx__0", "__idx__1", "__idx__2", "__idx__5"


@pytest.fixture
def start(page, app_url, console_log):
    page.goto(app_url)
    wait_app_ready(page)
    return page


def wait_status_contains(page, text):
    page.wait_for_function("(s) => document.getElementById('status').textContent.includes(s)", arg=text)


def reset_and_settle(page):
    """初期設定に戻し（確認は accept）、読み直しと描画が終わるまで待つ。"""
    before, loads = settings_applied(page), load_count(page)
    reset_settings(page)
    wait_settings_applied(page, before + 1)
    wait_load_count(page, loads + 1)
    wait_settled(page)


def select_files(page, paths):
    """「ファイルを選択」（置き換え）。読み込みと描画の終了まで待つ。"""
    before = load_count(page)
    page.set_input_files("#fileInput", [str(p) for p in paths])
    wait_load_count(page, before + 1)
    wait_settled(page)


def write_json(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_round_trip_restores_figure_code_and_form(start, fixtures_dir, tmp_path):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "往復テスト")
    page.select_option("#colorPalette", "tab10")
    page.select_option("#plotType", "scatter")
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", LO)
    add_annotation(page, "hline", y="2")
    page.select_option("#figUnit", "cm")
    set_save_dpi(page, 200)
    page.fill("#saveFilename", "result")
    set_layout(page, 2, 1)
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-x", X)
    page.select_option("#series-s2-y", OTHER)
    set_series_panel(page, "s2", 1)
    wait_settled(page)
    wait_code_generated(page)
    summary, code, state_before = image_summary(page), code_text(page), app_state(page)
    assert len(summary) >= 2  # 2 パネル

    filename, saved = save_settings_file(page)
    assert filename == "result_settings.json"
    assert saved["format"] == "matplotlib-gui-settings"
    assert saved["files"] == [{"name": "band.csv", "sheet": "", "columns": 6}]
    assert status_kind(page) == "ok" and "result_settings.json" in status_text(page)
    path = tmp_path / filename
    path.write_text(json.dumps(saved), encoding="utf-8")

    reset_and_settle(page)
    assert page.input_value("#title") == "" and page.input_value("#figUnit") == "in"
    assert page.input_value("#layoutRows") == "1" and image_summary(page) != summary

    load_settings_file(page, path)
    wait_code_generated(page)
    assert image_summary(page) == summary
    assert code_text(page) == code
    assert app_state(page)["plot"] == state_before["plot"]
    # フォームの欄
    assert page.input_value("#title") == "往復テスト"
    assert page.input_value("#figUnit") == "cm"
    assert page.input_value("#colorPalette") == "tab10"
    assert page.input_value("#plotType") == "scatter"
    assert page.input_value("#saveDpi") == "custom" and page.input_value("#saveDpiCustom") == "200"
    assert page.input_value("#saveFilename") == "result"
    assert page.input_value("#layoutRows") == "2" and page.input_value("#layoutCols") == "1"
    assert page.input_value("#series-s1-y") == LO and page.input_value("#series-s2-y") == OTHER
    assert page.input_value("#series-s2-panel") == "1" and page.input_value("#series-s1-panel") == "0"
    assert len(state_list(page, "annotations")) == 1 and page.is_visible("#annotation-a1-kind")


def test_default_filename_is_plot_settings(start, fixtures_dir):
    page = start
    filename, saved = save_settings_file(page)  # データが無くても保存できる
    assert filename == "plot_settings.json"
    assert saved["files"] == [] and saved["settings"]["version"] == 4


def test_apply_to_other_files_by_column_count(start, fixtures_dir, tmp_path):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", OTHER)
    wait_settled(page)
    _, saved = save_settings_file(page)
    path = write_json(tmp_path, "s.json", saved)

    # 同じ列数のファイル: 同じ列を使う
    select_files(page, [fixtures_dir / "chart_types.csv"])
    reset_and_settle(page)
    load_settings_file(page, path)
    s1 = series_state(page, "s1")
    assert (s1["x"], s1["y"]) == (X, OTHER)
    assert status_kind(page) != "error", status_text(page)

    # 列の少ないファイル（3 列）: 無い列は自動に戻る
    select_files(page, [fixtures_dir / "utf8.csv"])
    reset_and_settle(page)
    load_settings_file(page, path)
    s1 = series_state(page, "s1")
    assert s1["x"] == X and s1["y"] == ""
    assert image_summary(page) is not None


def save_two_file_settings(page, fixtures_dir, tmp_path):
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    add_files(page, [fixtures_dir / "chart_types.csv"])
    add_series_with_source(page, "d2", y="__idx__1")
    page.fill("#title", "2 ファイル")
    wait_settled(page)
    _, saved = save_settings_file(page)
    assert [f["columns"] for f in saved["files"]] == [6, 6]
    assert [s["source"] for s in saved["settings"]["series"]] == ["", "d2"]
    return write_json(tmp_path, "two.json", saved)


def test_two_files_saved_one_file_loaded_falls_back_to_data1(start, fixtures_dir, tmp_path):
    page = start
    path = save_two_file_settings(page, fixtures_dir, tmp_path)
    page.click("#file-d2-remove")
    wait_settled(page)
    assert series_state(page, "s2")["source"] == ""
    load_settings_file(page, path)
    s2 = series_state(page, "s2")
    assert s2["source"] == "" and s2["y"] == ""
    assert any("系列2: 設定のデータ2に当たるファイルが無いため、データ元をデータ1に戻し、列を自動に戻しました。" in w for w in status_warnings(page)), status_warnings(page)
    assert page.input_value("#title") == "2 ファイル"
    assert status_kind(page) != "error"
    assert image_summary(page) is not None


def test_two_files_loaded_in_other_order_map_by_position(start, fixtures_dir, tmp_path):
    page = start
    path = save_two_file_settings(page, fixtures_dir, tmp_path)
    select_files(page, [fixtures_dir / "errorbars.csv", fixtures_dir / "growth.csv"])
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    load_settings_file(page, path)
    assert series_state(page, "s2")["source"] == "d2" and series_state(page, "s2")["y"] == "__idx__1"
    assert "growth.csv" in page.inner_text("#file-d2")
    assert not any("当たるファイルが無い" in w for w in status_warnings(page))
    assert status_kind(page) != "error", status_text(page)
    assert image_summary(page)[0]["lines"] == 2


def test_computed_column_index_follows_file_column_count(start, fixtures_dir, tmp_path):
    page = start
    load_fixture(page, fixtures_dir / "chart_types.csv")  # 6 列。最初の計算した列は [6]
    wait_settled(page)
    add_computed(page, "[1] * 2", "2倍")
    page.select_option("#series-s1-y", "__idx__6")
    wait_settled(page)
    _, saved = save_settings_file(page)
    assert saved["files"][0]["columns"] == 6
    path = write_json(tmp_path, "c.json", saved)

    for fixture, expected in (("utf8.csv", "__idx__3"), ("errorbars.csv", "__idx__7")):
        select_files(page, [fixtures_dir / fixture])
        reset_and_settle(page)
        load_settings_file(page, path)
        assert series_state(page, "s1")["y"] == expected, fixture
        assert [c["expr"] for c in state_list(page, "computed")] == ["[1] * 2"]
        assert status_kind(page) != "error", status_text(page)
        assert image_summary(page) is not None


@pytest.mark.parametrize(
    "kind, message",
    [
        ("big", "設定ファイルが大きすぎます（1 MB まで）。"),
        ("notjson", "JSON の形式ではありません。"),
        ("newer", "新しい版のアプリで作られたため"),
    ],
)
def test_invalid_settings_file_changes_nothing(start, fixtures_dir, tmp_path, kind, message):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "そのまま")
    wait_settled(page)
    contents = {
        "big": "x" * (1024 * 1024 + 10),
        "notjson": "これは JSON ではありません {",
        "newer": json.dumps({"format": "matplotlib-gui-settings", "files": [], "settings": {"version": 5, "plot": {"title": "新"}}}),
    }
    path = write_json(tmp_path, f"{kind}.json", contents[kind])
    state, summary, generation, applied = app_state(page), image_summary(page), image_generation(page), settings_applied(page)
    load_settings_file(page, path, wait=None)
    wait_status_contains(page, message)
    assert status_kind(page) == "error"
    page.wait_for_timeout(600)
    assert app_state(page) == state and image_summary(page) == summary
    assert image_generation(page) == generation and settings_applied(page) == applied
    assert page.input_value("#title") == "そのまま"


def test_edit_mode_changes_gui_but_not_figure_or_code(start, fixtures_dir, tmp_path):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "保存した題")
    wait_settled(page)
    _, saved = save_settings_file(page)
    path = write_json(tmp_path, "e.json", saved)
    page.fill("#title", "別の題")
    wait_settled(page)
    wait_code_generated(page)
    enter_edit_mode(page)
    generation, code, summary = image_generation(page), code_text(page), image_summary(page)
    load_settings_file(page, path)
    assert page.input_value("#title") == "保存した題"
    assert app_state(page)["plot"]["title"] == "保存した題"
    assert image_generation(page) == generation and image_summary(page) == summary
    assert code_text(page) == code and "別の題" in code
    assert "編集" in status_text(page)


def test_auto_restore_applies_after_selecting_file(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "前回の題")
    page.select_option("#plotType", "scatter")
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", LO)
    wait_settled(page)
    wait_last_settings(page, "前回の題")
    raw = last_settings_raw(page)
    assert "band.csv" not in raw
    stored = json.loads(raw)
    assert stored["files"] == [{"columns": 6}] and stored["settings"]["load"]["files"] == []

    page.reload()
    wait_app_ready(page)
    assert settings_applied(page) == 1
    assert status_kind(page) == "ok" and "前回の設定を復元しました。" in status_text(page)
    assert page.input_value("#title") == "前回の題" and page.input_value("#plotType") == "scatter"
    assert series_state(page, "s1")["y"] == LO  # 列の選択肢はファイルを読むまで無いので、欄ではなく state で確かめる

    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    s = image_summary(page)[0]
    assert s["title"] == "前回の題" and s["collections"] >= 1
    assert series_state(page, "s1")["y"] == LO


def test_auto_restore_maps_multi_file_sources_by_position(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    add_files(page, [fixtures_dir / "chart_types.csv"])
    add_series_with_source(page, "d2", y="__idx__1")
    wait_last_settings(page, '"d2"')

    page.reload()
    wait_app_ready(page)
    assert "前回の設定を復元しました。" in status_text(page)
    assert [s["source"] for s in app_state(page)["series"]] == ["", "d2"]
    page.set_input_files("#fileInput", [str(fixtures_dir / "band.csv"), str(fixtures_dir / "chart_types.csv")])
    wait_load_count(page, 1)
    wait_settled(page)
    assert file_row_ids(page) == ["file-d1", "file-d2"]
    assert series_state(page, "s2")["source"] == "d2" and series_state(page, "s2")["y"] == "__idx__1"
    assert not any("当たるファイルが無い" in w for w in status_warnings(page))
    assert status_kind(page) != "error", status_text(page)


def test_unreadable_stored_value_warns_and_is_removed(start):
    page = start
    for stored in ("これは壊れた値", json.dumps({"format": "matplotlib-gui-settings", "files": [], "settings": {"version": 9, "plot": {}}})):
        page.evaluate("([k, v]) => localStorage.setItem(k, v)", ["mplgui.lastSettings", stored])
        page.reload()
        wait_app_ready(page)
        assert status_kind(page) == "warning"
        assert "前回の設定を読めなかったため、初期設定で始めます。" in status_text(page)
        assert last_settings_raw(page) is None
        assert settings_applied(page) == 0
        assert page.input_value("#title") == ""


def test_works_when_local_storage_throws(page, app_url, fixtures_dir, tmp_path, console_log):
    page.add_init_script(
        """
        Storage.prototype.getItem = function () { throw new Error('blocked'); };
        Storage.prototype.setItem = function () { throw new Error('blocked'); };
        Storage.prototype.removeItem = function () { throw new Error('blocked'); };
        """
    )
    page.goto(app_url)
    wait_app_ready(page)
    assert status_kind(page) != "warning" and settings_applied(page) == 0
    load_fixture(page, fixtures_dir / "utf8.csv")
    wait_settled(page)
    page.fill("#title", "保存できる")
    wait_settled(page)
    page.wait_for_timeout(700)  # 控えの書き込みが失敗しても動くこと
    filename, saved = save_settings_file(page)
    path = write_json(tmp_path, filename, saved)
    reset_and_settle(page)
    assert page.input_value("#title") == ""
    load_settings_file(page, path)
    assert page.input_value("#title") == "保存できる"
    assert status_kind(page) != "error", status_text(page)
    assert [e for e in console_log.events if "blocked" in e[3]] == []


def test_reset_confirm_restores_defaults_and_removes_stored_value(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "戻される題")
    page.select_option("#plotType", "scatter")
    wait_settled(page)
    wait_last_settings(page, "戻される題")
    message = reset_settings(page)
    assert "すべての設定を初期状態に戻します" in message
    wait_settings_applied(page, 1)
    wait_settled(page)
    assert app_state(page)["plot"]["title"] == "" and page.input_value("#plotType") == "line"
    assert [s["id"] for s in app_state(page)["series"]] == ["s1"]
    wait_last_settings_removed(page)
    page.reload()
    wait_app_ready(page)
    assert settings_applied(page) == 0 and "復元" not in status_text(page)
    assert page.input_value("#title") == ""


def test_reset_dismissed_changes_nothing(start, fixtures_dir):
    page = start
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.fill("#title", "残る題")
    wait_settled(page)
    state, summary = app_state(page), image_summary(page)
    reset_settings(page, accept=False)
    page.wait_for_timeout(700)
    assert settings_applied(page) == 0
    assert app_state(page) == state and image_summary(page) == summary
    assert page.input_value("#title") == "残る題"


def test_narrow_screen_buttons_wrap_without_horizontal_scroll(page, app_url, fixtures_dir, console_log):
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    ids = ["saveSettingsBtn", "loadSettingsBtn", "resetSettingsBtn"]
    for i in ids:
        page.locator(f"#{i}").scroll_into_view_if_needed()
        assert page.is_visible(f"#{i}")
    info = page.evaluate(
        """(ids) => {
          const group = document.querySelector('.settings-actions').getBoundingClientRect();
          const boxes = ids.map((i) => document.getElementById(i).getBoundingClientRect());
          return {
            page: document.documentElement.scrollWidth - window.innerWidth,
            inside: boxes.every((b) => b.left >= group.left - 1 && b.right <= group.right + 1),
            tops: [...new Set(boxes.map((b) => Math.round(b.top)))].length,
          };
        }""",
        ids,
    )
    assert info["page"] <= 0 and info["inside"]
    assert info["tops"] >= 2  # 1 行に収まらないので折り返す
