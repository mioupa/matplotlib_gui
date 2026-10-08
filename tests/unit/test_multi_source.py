"""Phase 4 D6（複数ファイル）の単体テスト: Session、データ元の解決、描画計画、生成コード、注入対策。"""
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from mplgui import api
from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot
from mplgui.errors import UserError
from mplgui.loader import load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def fresh_session(tmp_path):
    api.SESSION.forget()
    api.SESSION.workdir = tmp_path / "work"
    api.SESSION.workdir.mkdir()
    yield
    api.SESSION.forget()
    api.SESSION.workdir = None


def files_settings(*entries, series=None, **plot):
    s = default_settings()
    s["load"]["files"] = [{"id": i, "name": n, "sheet": sh} for i, n, sh in entries]
    s["series"] = series or [{"x": "", "y": "__idx__1"}]
    s["plot"].update(plot)
    return s


def load(name, sid, settings, data=None, pasted=False):
    raw = data if data is not None else (FIXTURES / name).read_bytes()
    return json.loads(api.load_file_json(name, raw, json.dumps(settings), sid, pasted))


TWO = (("d1", "utf8.csv", ""), ("d2", "growth.csv", ""))


def load_two(settings):
    assert load("utf8.csv", "d1", settings)["ok"]
    assert load("growth.csv", "d2", settings)["ok"]


# ---------------------------------------------------------------- Session


def test_session_add_replace_remove_clear_and_workfolder():
    s = files_settings(*TWO)
    load_two(s)
    work = api.SESSION.workdir
    assert set(api.SESSION.sources) == {"d1", "d2"}
    assert (work / "utf8.csv").exists() and (work / "growth.csv").exists()
    # 同じ id を別のファイルで置き換える: 古い作業フォルダのファイルは消え、d2 は残る
    s2 = files_settings(("d1", "tab.txt", ""), ("d2", "growth.csv", ""))
    assert load("tab.txt", "d1", s2)["ok"]
    assert not (work / "utf8.csv").exists() and (work / "tab.txt").exists() and (work / "growth.csv").exists()
    assert api.SESSION.sources["d1"].name == "tab.txt" and "d2" in api.SESSION.sources
    assert json.loads(api.remove_source_json("d2")) == {"ok": True}
    assert set(api.SESSION.sources) == {"d1"} and not (work / "growth.csv").exists()
    assert json.loads(api.remove_source_json("zzz")) == {"ok": True}  # 無い id でも失敗しない
    load_two(s)
    assert json.loads(api.clear_sources_json()) == {"ok": True}
    assert api.SESSION.sources == {} and list(work.iterdir()) == []


def test_failure_of_one_source_keeps_others():
    s = files_settings(*TWO)
    load_two(s)
    r = json.loads(api.load_file_json("memo.json", b"{}", json.dumps(s), "d2"))
    assert r["ok"] is False
    assert set(api.SESSION.sources) == {"d1"}


def test_same_name_in_two_sources_keeps_the_file_until_both_removed():
    s = files_settings(("d1", "utf8.csv", ""), ("d2", "utf8.csv", ""))
    load("utf8.csv", "d1", s)
    load("utf8.csv", "d2", s)
    api.remove_source_json("d1")
    assert (api.SESSION.workdir / "utf8.csv").exists()
    api.remove_source_json("d2")
    assert not (api.SESSION.workdir / "utf8.csv").exists()


def test_excel_cache_is_per_source():
    s = files_settings(("d1", "multi_sheet.xlsx", ""), ("d2", "multi_sheet.xlsx", "二枚目"))
    load("multi_sheet.xlsx", "d1", s)
    load("multi_sheet.xlsx", "d2", s)
    assert set(api.SESSION.excels) == {"d1", "d2"}
    assert api.SESSION.excels["d1"][1] is not api.SESSION.excels["d2"][1]
    api.SESSION.forget()
    assert api.SESSION.excels == {}


# ---------------------------------------------------------------- source resolution


def render(settings):
    return json.loads(api.render_json(json.dumps(settings)))


def test_no_source_loaded_is_the_usual_message():
    r = render(files_settings(*TWO))
    assert r["ok"] is False and "先にファイルを読み込んでください" in r["error"]["message"]


def test_empty_source_means_first_file_and_series_use_their_own_source():
    s = files_settings(*TWO, series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__2", "source": "d2"}])
    load_two(s)
    r = render(s)
    assert r["ok"] and r["seriesCount"] == 2
    # 系列1は utf8.csv の2列目（電圧）、系列2は growth.csv の3列目（線形）
    assert "df1.iloc[:, 1]" in r["code"] and "df2.iloc[:, 2]" in r["code"]
    assert r["summary"][0]["lines"] == 2


def test_failed_source_used_by_a_series_is_a_user_error():
    s = files_settings(*TWO, series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__2", "source": "d2"}])
    load("utf8.csv", "d1", s)  # d2 は読み込めていない
    r = render(s)
    assert r["ok"] is False
    assert r["error"]["message"] == "データ2（growth.csv）を読み込めていません。読込設定やファイルを確認してください。"
    assert r["error"]["field"] == "系列2のデータ元"


def test_first_source_failed_means_empty_source_series_error():
    s = files_settings(*TWO)
    load("growth.csv", "d2", s)
    r = render(s)
    assert r["ok"] is False and "データ1（utf8.csv）を読み込めていません" in r["error"]["message"]
    assert r["error"]["field"] == "系列1のデータ元"


def test_without_files_list_the_first_loaded_source_is_used():
    s = default_settings()
    load("utf8.csv", "d1", s)
    r = render(s)
    assert r["ok"] and "DATA_FILE =" in r["code"] and "df = pd.read_csv" in r["code"]


# ---------------------------------------------------------------- dataprep


def frames():
    return {
        "d1": pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [5.0, 6.0, 7.0, 8.0]}),
        "d2": pd.DataFrame({"t": [10.0, 20.0, 30.0], "u": [1.0, 2.0, 3.0], "v": [4.0, 5.0, 6.0]}),
    }


def parsed(**kw):
    s = files_settings(("d1", "a.csv", ""), ("d2", "b.csv", ""), **kw.pop("plot", {}))
    s.update(kw)
    return parse_settings(s)


def test_dataprep_skip_rows_per_frame_and_y_auto_per_source():
    settings = parsed(
        series=[{"x": "", "y": ""}, {"x": "", "y": "", "source": "d2"}, {"x": "", "y": "", "source": "d2"}],
        plot={"skipRows": 1},
    )
    plan = plan_plot(frames(), settings)
    assert [s.data_var for s in plan.series] == ["df1", "df2", "df2"]
    # Y の自動割り当てはデータ元ごと（d1 は a, d2 は t と u）
    assert [(s.data_id, s.y_index) for s in plan.series] == [("d1", 0), ("d2", 0), ("d2", 1)]
    assert [src.var for src in plan.sources] == ["df1", "df2"] and plan.multi_source


def test_dataprep_skip_rows_error_uses_the_frame_that_is_too_short():
    settings = parsed(series=[{"x": "", "y": "", "source": "d2"}], plot={"skipRows": 3})
    with pytest.raises(UserError):
        plan_plot(frames(), settings)


def test_dataprep_bar_requires_same_source():
    settings = parsed(series=[{"x": "", "y": ""}, {"x": "", "y": "", "source": "d2"}], plot={"type": "bar"})
    with pytest.raises(UserError) as e:
        plan_plot(frames(), settings)
    assert e.value.message == "棒グラフでは、すべての系列に同じデータ元を選んでください。" and e.value.field == "データ元"
    ok = parsed(series=[{"x": "", "y": "", "source": "d2"}, {"x": "", "y": "", "source": "d2"}], plot={"type": "bar", "xColumn": "__idx__0"})
    plan = plan_plot(frames(), ok)
    assert plan.bar_x_index == 0 and {s.data_var for s in plan.series} == {"df2"}


def test_dataprep_unknown_and_missing_source_errors():
    settings = parsed(series=[{"x": "", "y": "", "source": "d2"}])
    only_first = {"d1": frames()["d1"]}
    with pytest.raises(UserError) as e:
        plan_plot(only_first, settings)
    assert "データ2（b.csv）を読み込めていません" in e.value.message and e.value.field == "系列1のデータ元"
    with pytest.raises(UserError) as e:
        plan_plot({}, settings)
    assert "先にファイルを読み込んでください" in e.value.message


def test_dataprep_datetime_rules_across_series():
    dt = pd.DataFrame({"t": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]), "v": [1.0, 2.0, 3.0]})
    data = {"d1": dt, "d2": frames()["d2"]}
    settings = parsed(series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__1", "source": "d2"}])
    with pytest.raises(UserError) as e:
        plan_plot(data, settings)
    assert "日時" in e.value.message


def test_single_dataframe_input_still_works():
    plan = plan_plot(frames()["d1"], parse_settings(default_settings()))
    assert plan.series[0].data_var == "df" and not plan.multi_source and plan.sources[0].var == "df"


# ---------------------------------------------------------------- codegen


def make(settings_raw, names):
    """names: {id: ファイル名}。fixtures を tmp に置く前提で、loader の結果から script を作る。"""
    settings = parse_settings(settings_raw)
    loaded = {sid: load_file((FIXTURES / n).read_bytes(), n, "", True, sheet=sh) for sid, n, sh in
              [(i, names[i], next(f["sheet"] for f in settings_raw["load"]["files"] if f["id"] == i)) for i in names]}
    plan = plan_plot({k: v.df for k, v in loaded.items()}, settings)
    return settings, loaded, plan, generate_script(settings, {k: v.source for k, v in loaded.items()}, plan)


def run_both(script, loaded, plan, cwd):
    with run_script(script.text, cwd=cwd) as r:
        full = figure_summary(r.fig)
    injected = {src.var: loaded[src.id].df for src in plan.sources}
    with run_script(script.auto_render_text(), injected=injected) as r:
        auto = figure_summary(r.fig)
    return full, auto


def test_two_source_script_names_numbering_and_summary(tmp_path):
    raw = files_settings(*TWO, series=[{"x": "", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__2", "source": "d2"}])
    settings, loaded, plan, script = make(raw, {"d1": "utf8.csv", "d2": "growth.csv"})
    text = script.text
    for name in ("utf8.csv", "growth.csv"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    assert 'DATA_FILE_1 = "utf8.csv"' in text and 'DATA_FILE_2 = "growth.csv"' in text
    assert "df1 = pd.read_csv(" in text and "df2 = pd.read_csv(" in text
    assert "# データ1: utf8.csv" in text and "# データ2: growth.csv" in text
    assert "df2.iloc[:, 2]" in text and "「utf8.csv」「growth.csv」" in text
    assert "DATA_FILE =" not in text
    full, auto = run_both(script, loaded, plan, tmp_path)
    assert full == auto and full[0]["lines"] == 2
    # 読込部は番号付きの両方の行を空行にする
    start, end = script.load_lines
    assert all(line == "" for line in script.auto_render_text().split("\n")[start - 1:end])


def test_only_used_sources_are_emitted_and_numbering_is_the_position(tmp_path):
    raw = files_settings(*TWO, series=[{"x": "", "y": "__idx__1", "source": "d2"}])
    settings, loaded, plan, script = make(raw, {"d1": "utf8.csv", "d2": "growth.csv"})
    assert "DATA_FILE_2" in script.text and "DATA_FILE_1" not in script.text and "df1" not in script.text
    assert "df2.iloc[:, 1]" in script.text
    shutil.copy(FIXTURES / "growth.csv", tmp_path / "growth.csv")
    full, auto = run_both(script, loaded, plan, tmp_path)
    assert full == auto


def test_skip_rows_trims_each_used_frame(tmp_path):
    raw = files_settings(*TWO, series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__1", "source": "d2"}], skipRows=2)
    _, loaded, plan, script = make(raw, {"d1": "utf8.csv", "d2": "growth.csv"})
    assert "df1 = df1.iloc[2:].reset_index(drop=True)" in script.text and "df2 = df2.iloc[2:].reset_index(drop=True)" in script.text
    for name in ("utf8.csv", "growth.csv"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    full, auto = run_both(script, loaded, plan, tmp_path)
    assert full == auto


def test_read_blocks_reproduce_each_loader_frame(tmp_path):
    """読込部だけを実行して、loader の DataFrame と一致する（csv + xlsx の2枚目のシート）。"""
    raw = files_settings(("d1", "utf8.csv", ""), ("d2", "multi_sheet.xlsx", "二枚目"),
                         series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__1", "source": "d2"}])
    _, loaded, plan, script = make(raw, {"d1": "utf8.csv", "d2": "multi_sheet.xlsx"})
    for name in ("utf8.csv", "multi_sheet.xlsx"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    start, end = script.load_lines
    lines = script.text.split("\n")[start - 1:end]
    ns: dict = {}
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        exec("import pandas as pd\n" + "\n".join(lines), ns)
    finally:
        os.chdir(cwd)
    pd.testing.assert_frame_equal(ns["df1"], loaded["d1"].df)
    pd.testing.assert_frame_equal(ns["df2"], loaded["d2"].df)
    assert 'sheet_name="二枚目"' in script.text
    full, auto = run_both(script, loaded, plan, tmp_path)
    assert full == auto


def test_pasted_and_file_sources_note_each_one(tmp_path):
    pasted = b"a\tb\n1\t2\n3\t4\n5\t7\n"
    s = files_settings(("d1", "pasted_data.tsv", ""), ("d2", "growth.csv", ""),
                       series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__1", "source": "d2"}])
    load("pasted_data.tsv", "d1", s, data=pasted, pasted=True)
    load("growth.csv", "d2", s)
    r = render(s)
    assert r["ok"]
    text = r["code"]
    assert text.count("# 貼り付けたデータ: ") == 1 and "（貼り付けたデータを保存したもの）" in text
    assert "DATA_FILE_1 = \"pasted_data.tsv\"" in text and "DATA_FILE_2 = \"growth.csv\"" in text


def test_two_hostile_file_names_cannot_inject():
    evil1 = 'a"\nimport os; os.system("x")  #  .csv'
    evil2 = "b'''\nraise SystemExit\n.csv"
    s = files_settings(("d1", evil1, ""), ("d2", evil2, ""),
                       series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__1", "source": "d2"}])
    api.SESSION.workdir = None
    data = b"a,b\n1,2\n3,4\n5,7\n"
    assert load(evil1, "d1", s, data=data)["ok"] and load(evil2, "d2", s, data=data)["ok"]
    settings = parse_settings(s)
    plan = plan_plot({sid: src.df for sid, src in api.SESSION.sources.items()}, settings)
    script = generate_script(settings, {sid: src.info for sid, src in api.SESSION.sources.items()}, plan)
    import ast
    tree = ast.parse(script.text)
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "system" not in calls
    assert not any(isinstance(n, ast.Import) and any(a.name == "os" for a in n.names) for n in ast.walk(tree))
    assigned = {t.id: n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                for t in n.targets if isinstance(t, ast.Name)}
    assert assigned["DATA_FILE_1"] == evil1 and assigned["DATA_FILE_2"] == evil2


def test_single_file_script_is_unchanged_with_one_entry():
    s = files_settings(("d1", "utf8.csv", ""))
    load("utf8.csv", "d1", s)
    r = render(s)
    assert r["ok"] and "DATA_FILE = " in r["code"] and "df = pd.read_csv" in r["code"] and "DATA_FILE_1" not in r["code"]


def test_api_injects_dfn_for_each_used_source():
    s = files_settings(*TWO, series=[{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__2", "source": "d2"}])
    load_two(s)
    r = render(s)
    assert r["ok"] and r["warnings"] == [] and r["image"].startswith("data:image/png")
    out = json.loads(api.save_json(json.dumps(s)))
    assert out["ok"]


def test_edit_mode_reads_all_files_from_the_work_folder():
    s = files_settings(*TWO)
    load_two(s)
    code = (
        "import pandas as pd\nimport matplotlib.pyplot as plt\n"
        "a = pd.read_csv('utf8.csv'); b = pd.read_csv('growth.csv')\n"
        "fig, ax = plt.subplots(); ax.plot(a.iloc[:, 0], a.iloc[:, 1]); ax.plot(b.iloc[:, 0], b.iloc[:, 1])\n"
    )
    r = json.loads(api.render_json(json.dumps(s), code))
    assert r["ok"], r
