"""計算した列（Phase 5c, G6）: カード、式、系列の列の選択肢、削除・読み直し・データ元変更での参照の付け替え、エラーと復帰。
fixture は chart_types.csv（0 category / 1 a / 2 b / 3 c / 4 err / 5 m の 6 列。最初の計算した列は [6]）。"""
import pytest

from helpers import (
    add_annotation,
    add_computed,
    add_files,
    add_series_with_source,
    code_is_stale,
    code_text,
    computed_index_text,
    enter_edit_mode,
    image_generation,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    option_labels,
    series_state,
    set_errorbars,
    set_fill,
    set_plot_type,
    state_list,
    status_kind,
    status_text,
    status_warnings,
    wait_app_ready,
    wait_code_generated,
    wait_error_status,
    wait_settled,
)

pytestmark = pytest.mark.e2e


def start(page, app_url, fixtures_dir, fixture="chart_types.csv"):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / fixture)
    wait_settled(page)


def axis0(page):
    return image_summary(page)[0]


def test_add_expression_and_use_as_y(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    assert not is_hidden_by_id(page, "addComputedBtn") and page.inner_text("#addComputedBtn") == "+ 列を追加"
    c1 = add_computed(page, "[1] / max([1])", "正規化 a")
    assert computed_index_text(page, c1) == "列 [6] として使えます"
    assert is_hidden_by_id(page, f"computed-{c1}-source")  # 1 ファイルのときはデータ元を出さない
    assert page.get_attribute(f"#computed-{c1}-expr", "placeholder") == "[1] / max([1])"
    page.select_option("#series-s1-y", "__idx__6")
    wait_settled(page)
    assert status_kind(page) != "error", status_text(page)
    s = axis0(page)
    assert s["lines"] == 1 and s["ylim"][1] <= 1.1 and s["ylim"][0] >= 0  # 最大値で割ったので 0〜1
    assert s["ylabel"].startswith("正規化 a")
    wait_code_generated(page)
    code = code_text(page)
    assert "計算した列" in code and "df.insert(" in code and "正規化 a" in code


def test_template_buttons(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page)
    page.click(f"#computed-{c1}-tpl-normalize")
    assert page.input_value(f"#computed-{c1}-expr") == "[1] / max([1])"  # 系列1の Y が自動なら [1]
    page.select_option("#series-s1-y", "__idx__2")
    wait_settled(page)
    page.click(f"#computed-{c1}-tpl-normalize")
    assert page.input_value(f"#computed-{c1}-expr") == "[2] / max([2])"
    page.click(f"#computed-{c1}-tpl-offset")
    assert page.input_value(f"#computed-{c1}-expr") == "[2] - first([2])"
    page.click(f"#computed-{c1}-tpl-rolling")
    assert page.input_value(f"#computed-{c1}-expr") == "rolling_mean([2], 5)"
    assert state_list(page, "computed")[0]["expr"] == "rolling_mean([2], 5)"
    wait_settled(page)
    assert status_kind(page) != "error"
    # Y が計算した列のときは、ファイルの列ではないので [1]
    page.select_option("#series-s1-y", "__idx__6")
    page.click(f"#computed-{c1}-tpl-offset")
    assert page.input_value(f"#computed-{c1}-expr") == "[1] - first([1])"


def test_options_show_computed_in_every_column_select(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page, "[1] * 2", "二倍")
    page.select_option("#series-s1-x", "__idx__1")
    set_errorbars(page, "s1", "y", mode="column")
    set_fill(page, "s1", lower="__idx__2")
    set_plot_type(page, "scatterColor")
    selects = [
        "series-s1-x", "series-s1-y", "series-s1-yerr-column", "series-s1-yerr-column-minus", "series-s1-xerr-column",
        "series-s1-fill-lower", "series-s1-fill-upper", "series-s1-color-column",
    ]
    for sid in selects:
        labels = option_labels(page, sid)
        assert labels.get("__idx__6") == "二倍 [6]（計算）", sid
        assert "__idx__7" not in labels
    set_plot_type(page, "bar")
    assert option_labels(page, "xColumn").get("__idx__6") == "二倍 [6]（計算）"
    # 名前が空なら「計算N」（N はカードの番号）
    c2 = add_computed(page, "[2] * 2")
    assert option_labels(page, "series-s1-y").get("__idx__7") == "計算2 [7]（計算）"
    assert computed_index_text(page, c2) == "列 [7] として使えます"
    # データ確認の表には出さない
    headers = page.eval_on_selector_all(".data-table th", "els => els.map(e => e.textContent)")
    assert len(headers) == 7 and not any("計算" in h for h in headers)  # # + 6 列
    assert c1 == "c1"


def test_remove_computed_resets_series_and_shifts_later_references(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page, "[1] * 2", "二倍")
    c2 = add_computed(page, "[2] * 3", "三倍")
    page.select_option("#series-s1-y", "__idx__7")  # 後ろの列を使う
    wait_settled(page)
    before = axis0(page)
    assert status_kind(page) != "error"
    page.click(f"#computed-{c1}-remove")
    wait_settled(page)
    assert series_state(page, "s1")["y"] == "__idx__6"  # 詰める
    assert computed_index_text(page, c2) == "列 [6] として使えます"
    after = axis0(page)
    assert after["ylim"] == pytest.approx(before["ylim"]) and after["lines"] == before["lines"]
    assert status_kind(page) != "error"
    # 使っていた列を消すと、設定は空に戻り、注意が出る
    page.select_option("#series-s1-x", "__idx__6")
    set_fill(page, "s1", lower="__idx__6")
    wait_settled(page)
    page.click(f"#computed-{c2}-remove")
    wait_settled(page)
    s1 = series_state(page, "s1")
    assert s1["y"] == "" and s1["x"] == "" and s1["fill"]["lower"] == ""
    notes = [w for w in status_warnings(page) if "計算した列「三倍」を削除したため" in w]
    assert len(notes) == 1 and notes[0].startswith("系列1:")  # 系列ごとに1つ


def test_reload_with_extra_column_keeps_computed_reference(page, app_url, fixtures_dir, tmp_path, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page, "[1] / max([1])", "正規化")
    page.select_option("#series-s1-y", "__idx__6")
    wait_settled(page)
    before = axis0(page)
    lines = (fixtures_dir / "chart_types.csv").read_text(encoding="utf-8").splitlines()
    extra = [lines[0] + ",extra"] + [f"{ln},{i}" for i, ln in enumerate(lines[1:])]
    (tmp_path / "chart_types.csv").write_text("\n".join(extra) + "\n", encoding="utf-8")  # 同じ名前で列が1つ多い
    load_fixture(page, tmp_path / "chart_types.csv")
    wait_settled(page)
    assert series_state(page, "s1")["y"] == "__idx__7"  # 計算した列を指したまま
    assert computed_index_text(page, c1) == "列 [7] として使えます"
    assert status_kind(page) != "error"
    assert axis0(page)["ylim"] == pytest.approx(before["ylim"])


def test_reload_with_fewer_columns_resets_vanished_file_column(page, app_url, fixtures_dir, tmp_path, console_log):
    start(page, app_url, fixtures_dir)
    add_computed(page, "[1] / max([1])", "正規化")
    page.select_option("#series-s1-y", "__idx__6")  # 計算した列
    page.click("#addSeriesBtn")
    page.select_option("#series-s2-y", "__idx__5")  # 最後のファイルの列（m）
    wait_settled(page)
    lines = (fixtures_dir / "chart_types.csv").read_text(encoding="utf-8").splitlines()
    fewer = [",".join(ln.split(",")[:5]) for ln in lines]  # 列が1つ少ない（5 列）
    (tmp_path / "chart_types.csv").write_text("\n".join(fewer) + "\n", encoding="utf-8")
    load_fixture(page, tmp_path / "chart_types.csv")
    wait_settled(page)
    assert series_state(page, "s2")["y"] == ""  # 無くなった列は空（自動）に戻る。計算した列を指さない
    assert series_state(page, "s1")["y"] == "__idx__5"  # 計算した列は [5] になり、系列1はそれを指したまま
    assert status_kind(page) != "error", status_text(page)
    assert axis0(page)["lines"] == 2


def test_expression_error_and_recovery(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page, "[1] / (", "x")
    page.select_option("#series-s1-y", "__idx__6")
    wait_error_status(page)
    text = status_text(page)
    assert "計算した列1の式" in text and "文字目" in text
    assert code_is_stale(page)
    page.fill(f"#computed-{c1}-expr", "[1] / (1 + 1)")
    wait_settled(page)
    assert status_kind(page) != "error" and not code_is_stale(page)


def test_reference_to_other_computed_column_error(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_computed(page, "[1] * 2")
    c2 = add_computed(page, "[6] + 1")
    wait_error_status(page)
    assert "ほかの計算した列" in status_text(page) and "計算した列2の式" in status_text(page)
    page.fill(f"#computed-{c2}-expr", "[1] + 1")
    wait_settled(page)
    assert status_kind(page) != "error"


def test_two_files_computed_column_on_second_source(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    add_files(page, [fixtures_dir / "band.csv"])  # d2（x / mean / lo / hi / day / other の 6 列）
    wait_settled(page)
    c1 = add_computed(page, "[1] * 2", "平均の2倍", source="d2")
    assert not is_hidden_by_id(page, f"computed-{c1}-source")
    assert computed_index_text(page, c1) == "列 [6] として使えます"
    add_series_with_source(page, "d2", "__idx__6")
    assert option_labels(page, "series-s2-y").get("__idx__6") == "平均の2倍 [6]（計算）"
    assert "__idx__6" not in option_labels(page, "series-s1-y")  # データ1には計算した列が無い
    assert status_kind(page) != "error", status_text(page)
    assert axis0(page)["lines"] == 2
    wait_code_generated(page)
    assert "df2.insert(" in code_text(page)
    # データ元を変えると、元のデータ元で使っていた設定は空に戻る
    page.select_option(f"#computed-{c1}-source", "d1")
    wait_settled(page)
    assert series_state(page, "s2")["y"] == ""
    assert any("計算した列「平均の2倍」のデータ元を替えたため" in w for w in status_warnings(page))
    assert computed_index_text(page, c1) == "列 [6] として使えます"
    # ファイルを外すと、データ元は先頭に戻る
    page.select_option(f"#computed-{c1}-source", "d2")
    wait_settled(page)
    from helpers import remove_file

    remove_file(page, "d2")
    wait_settled(page)
    assert state_list(page, "computed")[0]["source"] == ""
    assert any("計算した列1: データ元のファイルを外したため" in w for w in status_warnings(page))
    assert status_kind(page) != "error"


def test_add_button_disabled_at_limit(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    for _ in range(20):
        page.click("#addComputedBtn")
    assert page.is_disabled("#addComputedBtn")
    assert len(state_list(page, "computed")) == 20


def test_edit_mode_does_not_redraw(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    c1 = add_computed(page, "[1] * 2")
    page.select_option("#series-s1-y", "__idx__6")
    wait_settled(page)
    wait_code_generated(page)
    enter_edit_mode(page)
    before = (image_generation(page), code_text(page))
    page.fill(f"#computed-{c1}-expr", "[1] * 5")
    add_computed(page, "[2]")
    page.wait_for_timeout(1000)
    assert (image_generation(page), code_text(page)) == before
    assert "編集" in status_text(page)


def test_narrow_screen_has_no_horizontal_scroll(page, app_url, fixtures_dir, console_log):
    page.set_viewport_size({"width": 375, "height": 800})
    start(page, app_url, fixtures_dir)
    add_files(page, [fixtures_dir / "band.csv"])
    wait_settled(page)
    add_computed(page, "rolling_mean([1], 5) + [2] * 1000 + [3] * 1000 + [4] * 1000", "とても長い名前の計算した列", source="d2")
    add_annotation(page, "hline", y="1")
    overflow = page.evaluate(
        """() => {
          const wide = [...document.querySelectorAll('.computed-item, .annotation-item')]
            .filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.id || e.className);
          return {page: document.documentElement.scrollWidth - window.innerWidth, wide};
        }"""
    )
    assert overflow["page"] <= 0 and overflow["wide"] == []
