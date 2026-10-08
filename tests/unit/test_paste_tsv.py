"""D1: .tsv の読込と、貼り付けたデータ（pasted_data.tsv）の扱い。"""
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from mplgui import api
from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot
from mplgui.errors import UserError
from mplgui.loader import SourceInfo, load_file
from mplgui.settings import default_settings, parse_settings

TSV = "時間\t電圧\r\n0\t1.5\r\n1\t2.5\r\n2\t3.5\r\n".replace("\r\n", "\n").encode("utf-8")


def test_tsv_default_delimiter_is_tab():
    r = load_file(TSV, "a.tsv", "", True)
    assert r.df.shape == (3, 2) and r.source.kind == "tsv" and r.source.separator == "\t"
    assert list(r.df.columns) == ["時間", "電圧"]


def test_tsv_values_with_spaces_stay_in_one_cell():
    r = load_file("名前\t値\nA B\t1\nC D\t2\n".encode(), "a.tsv", "", True)
    assert list(r.df.iloc[:, 0]) == ["A B", "C D"]


def test_tsv_explicit_delimiter_overrides():
    r = load_file(b"a;b\n1;2\n", "a.tsv", ";", True)
    assert r.df.shape == (1, 2) and r.source.separator == ";"


def test_unsupported_extension_message_mentions_tsv():
    with pytest.raises(UserError) as e:
        load_file(b"x", "a.json", "", True)
    assert "tsv" in e.value.message


def _script(source, df):
    settings = parse_settings({**default_settings(), "series": [{"x": "", "y": "__idx__1"}]})
    return generate_script(settings, source, plan_plot(df, settings))


def test_pasted_source_adds_comment_and_usage():
    r = load_file(TSV, "pasted_data.tsv", "", True)
    pasted = SourceInfo(**{**r.source.__dict__, "pasted": True})
    text = _script(pasted, r.df).text
    assert "# 貼り付けたデータ: 「データ読み込み」の「貼り付けたデータを保存」で pasted_data.tsv を保存し、このスクリプトと同じフォルダに置いてください。" in text
    assert "貼り付けたデータを保存した「pasted_data.tsv」" in text
    assert "# 形式: TSV（.tsv）" in text and r'sep="\t"' in text
    plain = _script(r.source, r.df).text
    assert "貼り付けたデータ" not in plain


def test_pasted_comment_is_safe_with_hostile_filename():
    r = load_file(TSV, "x.tsv", "", True)
    src = SourceInfo(**{**r.source.__dict__, "filename": "a\nimport os\nos.system('x').tsv", "pasted": True})
    text = _script(src, r.df).text
    compile(text, "s.py", "exec")
    assert "\nimport os\nos" not in text


def test_pasted_read_section_reproduces_loader(tmp_path):
    r = load_file(TSV, "pasted_data.tsv", "", True)
    src = SourceInfo(**{**r.source.__dict__, "pasted": True})
    script = _script(src, r.df)
    (tmp_path / "pasted_data.tsv").write_bytes(TSV)
    start, end = script.load_lines
    code = "import pandas as pd\n" + "\n".join(script.text.split("\n")[start - 1:end])
    ns, cwd = {}, Path.cwd()
    os.chdir(tmp_path)
    try:
        exec(compile(code, "load.py", "exec"), ns)
    finally:
        os.chdir(cwd)
    pd.testing.assert_frame_equal(ns["df"], r.df)


@pytest.fixture
def session():
    api.SESSION.forget()
    with tempfile.TemporaryDirectory() as d:
        api.SESSION.workdir = Path(d)
        yield api.SESSION
    api.SESSION.forget()
    api.SESSION.workdir = None


def _load(pasted):
    s = {"version": 3, "load": default_settings()["load"]}
    return json.loads(api.load_file_json("pasted_data.tsv", TSV, json.dumps(s), "d1", pasted))


def test_api_pasted_load_marks_source_and_writes_file(session):
    r = _load(True)
    assert r["ok"] and r["encoding"] == "utf-8" and len(r["columns"]) == 2
    assert session.source.pasted is True and session.source.kind == "tsv"
    assert (session.workdir / "pasted_data.tsv").read_bytes() == TSV
    code = json.loads(api.script_json(json.dumps(default_settings())))["code"]
    assert "貼り付けたデータ" in code


def test_api_not_pasted_by_default(session):
    r = _load(False)
    assert r["ok"] and session.source.pasted is False
