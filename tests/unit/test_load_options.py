"""Phase 4 のデータ取り込み（D2 シート / D3 ヘッダ前の行 / D4 桁区切り・小数点・コメント）の単体テスト。"""
import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from mplgui import api, loader
from mplgui.codegen import generate_script
from mplgui.dataprep import DECIMAL_HINT, THOUSANDS_HINT, plan_plot
from mplgui.errors import UserError
from mplgui.loader import SourceInfo, build_preview, load_file
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def L(name, delimiter="", has_header=True, **kw):
    return load_file((FIXTURES / name).read_bytes(), name, delimiter, has_header, **kw)


def csv_bytes(text):
    return text.encode("utf-8")


# ---------------------------------------------------------------- loader


def test_existing_positional_call_still_works():
    assert load_file((FIXTURES / "utf8.csv").read_bytes(), "utf8.csv", "", True).df.shape == (30, 3)


def test_skip_lines_csv_and_preamble():
    r = L("preamble.csv", skip_lines=3)
    assert list(r.df.columns) == ["時間", "電圧", "電流"] and len(r.df) == 30
    assert r.preamble_total == 3 and len(r.preamble_lines) == 3 and r.preamble_lines[0].startswith("装置")
    assert r.source.skip_lines == 3
    p = build_preview(r.df, preamble=(r.preamble_lines, r.preamble_total))
    assert p["preamble"] == {"lines": list(r.preamble_lines), "total": 3}


def test_no_skip_lines_gives_no_preamble():
    r = L("utf8.csv")
    assert r.preamble_total == 0 and build_preview(r.df)["preamble"] is None
    assert build_preview(r.df, preamble=((), 0))["preamble"] is None


def test_preamble_lines_are_capped_at_20():
    text = "\n".join(f"memo {i}" for i in range(30)) + "\nx,y\n1,2\n"
    r = load_file(csv_bytes(text), "m.csv", "", True, skip_lines=30)
    assert len(r.preamble_lines) == 20 and r.preamble_total == 30
    assert build_preview(r.df, preamble=(r.preamble_lines, r.preamble_total))["preamble"]["total"] == 30


def test_preamble_without_skip_lines_is_a_parse_error_with_hint():
    with pytest.raises(UserError) as e:
        L("preamble.csv")
    assert "ヘッダより前に読み飛ばす行数" in e.value.message and e.value.field == "区切り文字"


def test_skip_lines_too_large():
    with pytest.raises(UserError) as e:
        L("preamble.csv", skip_lines=500)
    assert "ヘッダより前に読み飛ばす行数" in e.value.message
    with pytest.raises(UserError) as e:
        L("preamble.xlsx", skip_lines=500)
    assert "ヘッダより前に読み飛ばす行数" in e.value.message


def test_comment_characters():
    r = L("comments.csv", comment="#")
    assert list(r.df.columns) == ["x", "y"] and len(r.df) == 10
    assert pd.api.types.is_numeric_dtype(r.df["y"]) and r.df["y"].tolist() == [i * i for i in range(10)]
    assert r.source.comment == "#"


def test_european_numbers():
    r = L("european.csv", ";", thousands=".", decimal=",")
    assert r.df["値"].iloc[0] == 1234.5 and r.df["値"].iloc[-1] == -1234567.5
    assert r.df["比"].iloc[-1] == -0.5 and r.df["比"].iloc[1] == 0.25
    assert r.source.thousands == "." and r.source.decimal == ","


def test_thousands_with_negative_and_quotes():
    r = L("thousands.csv", thousands=",")
    assert r.df["金額"].tolist()[:2] == [1234, 2468] and r.df["差額"].iloc[0] == -98765.5
    assert pd.api.types.is_numeric_dtype(r.df["金額"])


def test_thousands_vs_decimal_ambiguity():
    # 1.234,5（ヨーロッパ式）と 1,234.5（英米式）は、設定どおりに読まれる
    eu = load_file(csv_bytes("v\n1.234,5\n"), "a.csv", ";", True, thousands=".", decimal=",").df["v"][0]
    us = load_file(csv_bytes('v\n"1,234.5"\n'), "a.csv", ";", True, thousands=",", decimal=".").df["v"][0]
    assert eu == us == 1234.5


def test_empty_trailing_lines_are_ignored():
    r = load_file(csv_bytes("a,b\n1,2\n3,4\n\n\n"), "a.csv", "", True)
    assert len(r.df) == 2


def test_thousands_space_with_whitespace_separator_is_an_error():
    with pytest.raises(UserError) as e:
        load_file(csv_bytes("a b\n1 2\n"), "a.txt", "", True, thousands=" ")
    assert e.value.field == "桁区切り" and "空白" in e.value.message
    # 区切りが空白でなければ構わない
    r = load_file(csv_bytes("a;b\n1 234;2\n"), "a.txt", ";", True, thousands=" ")
    assert r.df["a"][0] == 1234


def test_comment_equal_to_separator_is_an_error():
    with pytest.raises(UserError) as e:
        load_file(csv_bytes("a;b\n1;2\n"), "a.csv", ";", True, comment=";")
    assert e.value.field == "コメント記号"


def test_delimiter_hint_warning():
    r = load_file(csv_bytes("a;b;c\n1;2;3\n"), "a.csv", "", True)
    assert r.df.shape[1] == 1 and len(r.warnings) == 1 and "区切り文字" in r.warnings[0]
    assert load_file(csv_bytes("a;b;c\n1;2;3\n"), "a.csv", ";", True).warnings == []
    assert load_file(csv_bytes("a\n1\n"), "a.csv", "", True).warnings == []
    tabbed = load_file(csv_bytes("a\tb\n1\t2\n"), "a.csv", "", True)
    assert tabbed.warnings
    # 説明の行を読み飛ばしたあとの先頭行で判定する
    r = load_file(csv_bytes("memo;memo\na;b\n1;2\n"), "a.csv", "", True, skip_lines=1)
    assert r.warnings


def test_no_header_with_options():
    r = load_file(csv_bytes("memo\n1,2\n3,4\n"), "a.csv", "", False, skip_lines=1)
    assert list(r.df.columns) == ["column_0", "column_1"] and len(r.df) == 2


# ---------------------------------------------------------------- xlsx


def test_xlsx_sheets_and_default_sheet():
    r = L("multi_sheet.xlsx")
    assert r.source.sheets == ("Sheet1", "二枚目") and r.source.sheet_name == "Sheet1"
    r2 = L("multi_sheet.xlsx", sheet="二枚目")
    assert r2.source.sheet_name == "二枚目" and list(r2.df.columns) == ["x", "y", "z"]
    assert r2.source.read_kwargs()["sheet_name"] == "二枚目"


def test_xlsx_missing_sheet():
    with pytest.raises(UserError) as e:
        L("multi_sheet.xlsx", sheet="ない")
    assert e.value.field == "シート" and "「ない」" in e.value.message


def test_xlsx_skip_lines_and_preamble():
    r = L("preamble.xlsx", sheet="説明つき", skip_lines=2)
    assert list(r.df.columns) == ["t", "v", "w"] and len(r.df) == 15
    assert r.preamble_lines == ("測定条件: 合成データ", "単位: V") and r.preamble_total == 2


def test_xlsx_other_options_are_accepted():
    r = L("multi_sheet.xlsx", thousands=",", decimal=",", comment="#")
    assert r.df.shape[0] == 30


def test_xlsx_uses_given_excel_object():
    excel = loader.open_excel((FIXTURES / "multi_sheet.xlsx").read_bytes())
    r = L("multi_sheet.xlsx", sheet="二枚目", excel=excel)
    assert r.df.shape == (20, 3)


def test_read_kwargs_is_shared_definition():
    src = SourceInfo(filename="a.csv", kind="csv", encoding="utf-8", separator=",", skip_lines=2, thousands=",", decimal=".", comment="#")
    assert list(src.read_kwargs()) == ["sep", "header", "skiprows", "thousands", "decimal", "comment", "engine"]
    xl = SourceInfo(filename="a.xlsx", kind="xlsx", sheet_name="S", has_header=False)
    assert xl.read_kwargs() == {"sheet_name": "S", "header": None, "skiprows": 0, "thousands": None, "decimal": ".", "comment": None}


# ---------------------------------------------------------------- generated load section equals the loader

CASES = [
    ("preamble.csv", "", dict(skip_lines=3)),
    ("preamble.csv", "", dict(skip_lines=3, has_header=False)),
    ("european.csv", ";", dict(thousands=".", decimal=",")),
    ("thousands.csv", "", dict(thousands=",")),
    ("comments.csv", "", dict(comment="#")),
    ("multi_sheet.xlsx", "", dict(sheet="二枚目")),
    ("preamble.xlsx", "", dict(sheet="説明つき", skip_lines=2)),
    ("preamble.xlsx", "", dict(sheet="データ", has_header=False)),
]


def load_section(script):
    start, end = script.load_lines
    return "import pandas as pd\n" + "\n".join(script.text.split("\n")[start - 1:end])


def exec_in(tmp_path, code):
    ns = {}
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        exec(compile(code, "load.py", "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns


@pytest.mark.parametrize("name, delimiter, opts", CASES)
def test_generated_load_section_matches_loader(tmp_path, name, delimiter, opts):
    opts = dict(opts)
    has_header = opts.pop("has_header", True)
    shutil.copy(FIXTURES / name, tmp_path / name)
    loaded = L(name, delimiter, has_header, **opts)
    settings = parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__1"}]})
    script = generate_script(settings, loaded.source, plan_plot(loaded.df, settings))
    ns = exec_in(tmp_path, load_section(script))
    pd.testing.assert_frame_equal(ns["df"], loaded.df)
    # 自動描画用の変種では、読込部がすべて空行になる
    auto = script.auto_render_text()
    assert "read_" not in auto and "DATA_FILE" not in auto and "skiprows" not in auto and "df.columns" not in auto


def test_read_section_text_has_every_option():
    loaded = L("european.csv", ";", thousands=".", decimal=",", skip_lines=0, comment="%")
    settings = parse_settings(default_settings())
    text = generate_script(settings, loaded.source, plan_plot(loaded.df, parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__1"}]}))).text
    assert (
        'df = pd.read_csv(\n'
        '    DATA_FILE,\n'
        '    encoding="utf-8",  # 文字コード（自動判定）\n'
        '    sep=";",  # 区切り文字\n'
        '    header=0,  # 先頭行をヘッダにする（None: ヘッダなし）\n'
        '    skiprows=0,  # ヘッダより前に読み飛ばす行数\n'
        '    thousands=".",  # 桁区切り（None: なし）\n'
        '    decimal=",",  # 小数点\n'
        '    comment="%",  # コメント記号（None: なし）。この記号から行末までを読まない\n'
        '    engine="python",\n'
        ')\n'
    ) in text
    xl = L("multi_sheet.xlsx", sheet="二枚目")
    text = generate_script(settings, xl.source, plan_plot(xl.df, parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__1"}]}))).text
    assert "# ファイル内のシート: Sheet1, 二枚目\n" in text
    assert 'df = pd.read_excel(\n    DATA_FILE,\n    sheet_name="二枚目",  # シート\n' in text
    assert "    thousands=None,  # 桁区切り（文字列のセルだけに効く。None: なし）\n" in text
    assert "    decimal=\".\",  # 小数点（文字列のセルだけに効く）\n" in text


# ---------------------------------------------------------------- injection

HOSTILE_NAMES = ['x"); import os; os.system("echo")  #', "a\nimport os\nos.system('echo')\n", "s\r\nraise SystemExit", "'''\nraise SystemExit"]


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
def test_hostile_sheet_and_file_names_do_not_inject(hostile):
    import ast

    src = SourceInfo(
        filename=hostile + ".xlsx", kind="xlsx", sheet_name=hostile, sheets=(hostile, "b\nc"), has_header=False,
        thousands=",", comment="#",
    )
    df = pd.DataFrame({"a": [1.0, 2.0]})
    settings = parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__0"}]})
    script = generate_script(settings, src, plan_plot(df, settings))
    tree = ast.parse(script.text)
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "") for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "system" not in calls and "__import__" not in calls
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(a.name == "os" for a in getattr(n, "names", [])) for n in ast.walk(tree))
    assert "SystemExit" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    # 読込部のコメントは1行に収まる
    start, end = script.load_lines
    for line in script.text.split("\n")[start - 1:end]:
        assert "\r" not in line


@pytest.mark.parametrize("comment", ["#", "%", ";", "\\", "'", "x"])
def test_comment_character_is_a_literal(comment):
    src = SourceInfo(filename="a.csv", kind="csv", encoding="utf-8", separator=",", comment=comment)
    df = pd.DataFrame({"a": [1.0, 2.0]})
    settings = parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__0"}]})
    script = generate_script(settings, src, plan_plot(df, settings))
    compile(script.text, "plot.py", "exec")
    start, end = script.load_lines
    section = "\n".join(script.text.split("\n")[start - 1:end])
    ns = {}
    code = section.replace("df = pd.read_csv(", "kw = dict(", 1).replace("    DATA_FILE,\n", "")
    exec("import pandas as pd\n" + code, ns)
    assert ns["kw"]["comment"] == comment


# ---------------------------------------------------------------- dataprep hints


def _plan_warning(text, **load):
    raw = default_settings()
    raw["load"].update(load)
    raw["series"] = [{"x": "", "y": "__idx__1"}]
    settings = parse_settings(raw)
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": text})
    return plan_plot(df, settings).warnings


def test_thousands_hint():
    w = _plan_warning(["1,234", "2,345", "5", "6"])
    assert w and THOUSANDS_HINT in w[0]["message"]
    w = _plan_warning(["-1,234,567.5", "2", "5", "6"])
    assert w and THOUSANDS_HINT in w[0]["message"]
    # すでにカンマを桁区切りにしているなら案内しない
    assert not any(THOUSANDS_HINT in x["message"] for x in _plan_warning(["1,234x", "2", "5", "6"], thousands=","))


def test_decimal_hint():
    w = _plan_warning(["1,5", "2", "5", "6"])
    assert w and DECIMAL_HINT in w[0]["message"] and THOUSANDS_HINT not in w[0]["message"]
    w = _plan_warning(["1.234,5", "2", "5", "6"])
    assert w and DECIMAL_HINT in w[0]["message"]
    assert not any(DECIMAL_HINT in x["message"] for x in _plan_warning(["1,5x", "2", "5", "6"], decimal=","))


def test_no_hint_for_ordinary_text():
    w = _plan_warning(["abc", "2", "5", "6"])
    assert w and "桁区切り" not in w[0]["message"] and "小数点" not in w[0]["message"]


# ---------------------------------------------------------------- api


@pytest.fixture(autouse=True)
def fresh_session():
    api.SESSION.forget()
    api.SESSION.workdir = None
    yield
    api.SESSION.forget()
    api.SESSION.workdir = None


def api_load(name, **load):
    s = default_settings()
    sheet = load.pop("sheet", None)
    s["load"].update(load)
    if sheet is not None:
        s["load"]["files"] = [{"id": "d1", "name": name, "sheet": sheet}]
    return json.loads(api.load_file_json(name, (FIXTURES / name).read_bytes(), json.dumps(s)))


def test_api_sheets_and_sheet():
    r = api_load("multi_sheet.xlsx")
    assert r["ok"] and r["sheets"] == ["Sheet1", "二枚目"] and r["sheet"] == "Sheet1"
    r = api_load("multi_sheet.xlsx", sheet="二枚目")
    assert r["sheet"] == "二枚目" and [c["label"] for c in r["columns"]] == ["x [0]", "y [1]", "z [2]"]
    r = api_load("utf8.csv")
    assert r["sheets"] == [] and r["sheet"] is None and r["preview"]["preamble"] is None


def test_api_missing_sheet_is_an_error():
    r = api_load("multi_sheet.xlsx", sheet="ない")
    assert r["ok"] is False and r["error"]["field"] == "シート"


def test_api_preamble_and_warnings():
    r = api_load("preamble.csv", skipLines=3)
    assert r["ok"] and r["preview"]["preamble"]["total"] == 3 and r["preview"]["preamble"]["lines"][0].startswith("装置")
    r = api_load("preamble.csv")
    assert r["ok"] is False and "ヘッダより前に読み飛ばす行数" in r["error"]["message"]
    r = json.loads(api.load_file_json("a.csv", b"a;b\n1;2\n", json.dumps(default_settings())))
    assert r["ok"] and len(r["warnings"]) == 1 and "区切り文字" in r["warnings"][0]


def test_api_load_options_reach_the_script():
    api_load("european.csv", delimiter=";", thousands=".", decimal=",")
    s = default_settings()
    s["load"].update(delimiter=";", thousands=".", decimal=",")
    s["series"] = [{"x": "", "y": "__idx__1"}]
    r = json.loads(api.render_json(json.dumps(s)))
    assert r["ok"] and 'thousands=".",' in r["code"] and 'decimal=",",' in r["code"] and not r["warnings"]


def test_api_reuses_excel_object_for_same_bytes(monkeypatch):
    opened = []
    real = loader.open_excel
    monkeypatch.setattr(loader, "open_excel", lambda raw: opened.append(1) or real(raw))
    api_load("multi_sheet.xlsx")
    api_load("multi_sheet.xlsx", sheet="二枚目")
    api_load("multi_sheet.xlsx", sheet="Sheet1")
    assert len(opened) == 1
    first = api.SESSION.excel
    # 別のファイルを読むとキャッシュを捨てる
    api_load("utf8.csv")
    assert api.SESSION.excel is None and first is not None
    api_load("multi_sheet.xlsx")
    assert len(opened) == 2
    api.SESSION.forget()
    assert api.SESSION.excel is None
    api_load("preamble.xlsx")
    assert len(opened) == 3


def test_api_excel_cache_survives_failed_load():
    api_load("multi_sheet.xlsx")
    excel = api.SESSION.excel
    r = api_load("multi_sheet.xlsx", sheet="ない")
    assert r["ok"] is False and api.SESSION.excel is excel
    assert api_load("multi_sheet.xlsx", sheet="二枚目")["ok"]
    assert api.SESSION.excel is excel


def test_settings_file_id_rejects_trailing_newline():
    raw = default_settings()
    raw["load"]["files"] = [{"id": "d1\n", "name": "a.csv", "sheet": ""}]
    with pytest.raises(UserError):
        parse_settings(raw)


@pytest.mark.parametrize("name, delimiter, opts", CASES[:7])
def test_full_script_and_auto_render_agree(tmp_path, name, delimiter, opts):
    from mplgui.runner import figure_summary, run_script

    opts = dict(opts)
    has_header = opts.pop("has_header", True)
    shutil.copy(FIXTURES / name, tmp_path / name)
    loaded = L(name, delimiter, has_header, **opts)
    settings = parse_settings({**default_settings(), "series": [{"x": "__idx__0", "y": "__idx__1"}]})
    script = generate_script(settings, loaded.source, plan_plot(loaded.df, settings))
    with run_script(script.text, cwd=tmp_path) as run:
        full = figure_summary(run.fig)
    with run_script(script.auto_render_text(), injected={"df": loaded.df}) as run:
        auto = figure_summary(run.fig)
    assert full == auto
