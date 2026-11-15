"""js/settings-io.js（設定の保存・読込の純粋な部分）と state.replaceSettings を node で検証する（node が無ければ skip）。"""
import copy
import json

import pytest

from mplgui.formats import build_filename
from mplgui.settings import default_settings, parse_settings

from test_js_modules import needs_node, run_node

pytestmark = pytest.mark.unit

IO_FILES = {"settings-io.js": "js/settings-io.js", "defaults.js": "js/defaults.js"}
STATE_FILES = {
    "state.js": "js/state.js",
    "defaults.js": "js/defaults.js",
    "palettes.js": "js/palettes.js",
    "presets.js": "js/presets.js",
    "chart-types.js": "js/chart-types.js",
}


def node_io(tmp_path, body: str, extra_imports: str = ""):
    script = f"""
    import * as io from "./settings-io.js";
    import {{ DEFAULT_SETTINGS, DEFAULT_SERIES }} from "./defaults.js";
    {extra_imports}
    const clone = (v) => JSON.parse(JSON.stringify(v));
    const attempt = (fn) => {{ try {{ return {{ ok: fn() }}; }} catch (e) {{ return {{ error: e.message, isIo: e instanceof io.SettingsFileError }}; }} }};
    {body}
    """
    return run_node(tmp_path, IO_FILES, script)


@needs_node
def test_round_trip_and_positional_ids(tmp_path):
    res = node_io(
        tmp_path,
        """
        const s = clone(DEFAULT_SETTINGS);
        s.load.files = [{id: "d3", name: "a.csv", sheet: ""}, {id: "d7", name: "b.xlsx", sheet: "S2"}];
        s.series = [{...clone(DEFAULT_SERIES), id: "s1", source: "d7"}, {...clone(DEFAULT_SERIES), id: "s2", source: ""}, {...clone(DEFAULT_SERIES), id: "s3", source: "d3"}];
        s.computed = [{id: "c1", source: "d7", name: "n", expr: "[0]"}, {id: "c2", source: "", name: "", expr: "[1]"}];
        s.plot.title = "T";
        const w = io.serializeSettings(s, [{name: "a.csv", sheet: "", columns: 4}, {name: "b.xlsx", sheet: "S2", columns: null}], {savedAt: "X"});
        const text = JSON.stringify(w, null, 2);
        const parsed = io.parseSettingsFile(text, {size: text.length});
        console.log(JSON.stringify({w, parsed, original: s}));
        """,
    )
    w, parsed, original = res["w"], res["parsed"], res["original"]
    assert w["format"] == "matplotlib-gui-settings" and w["savedAt"] == "X"
    assert w["files"] == [{"name": "a.csv", "sheet": "", "columns": 4}, {"name": "b.xlsx", "sheet": "S2", "columns": None}]
    assert [f["id"] for f in w["settings"]["load"]["files"]] == ["d1", "d2"]
    assert [s["source"] for s in w["settings"]["series"]] == ["d2", "", "d1"]
    assert [c["source"] for c in w["settings"]["computed"]] == ["d2", ""]
    # 保存 → 読込で、データ元の id 以外は元の設定に戻る
    expected = copy.deepcopy(original)
    expected["load"]["files"] = w["settings"]["load"]["files"]
    for s, ws in zip(expected["series"], w["settings"]["series"]):
        s["source"] = ws["source"]
    for c, wc in zip(expected["computed"], w["settings"]["computed"]):
        c["source"] = wc["source"]
    assert parsed["settings"] == expected
    assert parsed["files"] == [{"name": "a.csv", "sheet": "", "columns": 4}, {"name": "b.xlsx", "sheet": "S2", "columns": None}]
    assert original["load"]["files"][0]["id"] == "d3"  # 元の設定は書き換えない


@needs_node
def test_serialize_without_names_for_local_storage(tmp_path):
    res = node_io(
        tmp_path,
        """
        const s = clone(DEFAULT_SETTINGS);
        s.load.files = [{id: "d2", name: "secret.csv", sheet: "Sheet9"}];
        s.series[0].source = "d2";
        const w = io.serializeSettings(s, [{name: "secret.csv", sheet: "Sheet9", columns: 5}], {names: false});
        // ファイル未読込のまま持っている dN は、そのまま残る
        const t = clone(DEFAULT_SETTINGS); t.series[0].source = "d2";
        const w2 = io.serializeSettings(t, [{columns: 3}], {names: false});
        console.log(JSON.stringify({w, w2, text: JSON.stringify(w)}));
        """,
    )
    assert res["w"]["files"] == [{"columns": 5}]
    assert res["w"]["settings"]["load"]["files"] == []
    assert res["w"]["settings"]["series"][0]["source"] == "d1"
    assert "secret.csv" not in res["text"] and "Sheet9" not in res["text"]
    assert res["w2"]["settings"]["series"][0]["source"] == "d2" and res["w2"]["files"] == [{"columns": 3}]


@needs_node
def test_parse_errors(tmp_path):
    res = node_io(
        tmp_path,
        """
        const p = (text, opts) => attempt(() => io.parseSettingsFile(text, opts));
        console.log(JSON.stringify({
          big: p("{}", {size: 1024 * 1024 + 1}),
          bigOk: p(JSON.stringify({plot: {}}), {size: 1024 * 1024}),
          badJson: p("{oops"),
          array: p("[1,2]"),
          scalar: p("3"),
          empty: p("{}"),
          other: p(JSON.stringify({a: 1, b: [1]})),
          wrongFormat: p(JSON.stringify({format: "other", settings: {plot: {}}})),
          noSettings: p(JSON.stringify({format: "matplotlib-gui-settings", settings: 3})),
          v5: p(JSON.stringify({version: 5, plot: {}})),
          v0: p(JSON.stringify({version: 0, plot: {}})),
          vStr: p(JSON.stringify({version: "x", plot: {}})),
          wrappedV9: p(JSON.stringify({format: "matplotlib-gui-settings", settings: {version: 9, plot: {}}})),
          v1: p(JSON.stringify({version: 1, plot: {}})).ok !== undefined,
        }));
        """,
    )
    assert res["big"]["error"] == "設定ファイルが大きすぎます（1 MB まで）。" and res["big"]["isIo"]
    assert "ok" in res["bigOk"]
    assert res["badJson"]["error"] == "設定ファイルを読み込めませんでした: JSON の形式ではありません。"
    for key in ("array", "scalar", "empty", "other", "wrongFormat", "noSettings"):
        assert res[key]["error"].startswith("設定ファイルではありません。"), key
    assert res["v5"]["error"] == "この設定ファイルは新しい版のアプリで作られたため、読み込めません（version 5）。"
    assert res["wrappedV9"]["error"].endswith("（version 9）。")
    assert "バージョン" in res["v0"]["error"] and "バージョン" in res["vStr"]["error"]
    assert res["v1"] is True


@needs_node
def test_normalization(tmp_path):
    res = node_io(
        tmp_path,
        """
        const parse = (o) => io.parseSettingsFile(JSON.stringify(o)).settings;
        const missing = parse({plot: {title: "T", figure: {width: "12"}}, series: [{y: "__idx__2"}, "bad", {id: "s1"}, {id: "s1"}]});
        const unknown = parse({plot: {title: "x", bogus: 1, figure: {width: 9, zzz: 2}}, extra: 1, series: [{id: "s5", nope: true}]});
        const shape = parse({plot: 5, axes: [1], series: {a: 1}, save: {dpi: {x: 1}}, load: {files: 3}, annotations: "x", fits: null, computed: 7, load2: 1});
        const emptySeries = parse({plot: {}, series: []});
        const dups = parse({plot: {}, series: [{id: "s2"}, {id: "s2"}, {id: ""}], annotations: [{kind: "text"}, {id: "a1"}, {id: "a1"}], fits: [{}, {}], computed: [{expr: "[0]"}, {id: "c4", expr: "[1]"}, {expr: "[2]"}]});
        const panels = parse({plot: {panels: [{title: "a"}, 3, {xLabel: "x", junk: 1}]}});
        const scalars = parse({plot: {fontSize: null, title: 12}, axes: {x: {min: "1e"}}});
        console.log(JSON.stringify({missing, unknown, shape, emptySeries, dups, panels, scalars, defaults: DEFAULT_SETTINGS}));
        """,
    )
    d = res["defaults"]
    m = res["missing"]
    assert m["version"] == 4 and m["plot"]["title"] == "T"
    assert m["plot"]["figure"] == {"width": "12", "height": 6, "unit": "in"}  # 値は検査せず、そのまま
    assert m["plot"]["layout"] == d["plot"]["layout"] and m["save"] == d["save"]
    assert len(m["series"]) == 4 and m["series"][0]["y"] == "__idx__2" and m["series"][0]["errorBars"] == d["series"][0]["errorBars"]
    assert m["series"][1]["id"] != "" and len({s["id"] for s in m["series"]}) == 4
    assert m["series"][2]["id"] == "s1"  # 先に出てきた id は保つ
    u = res["unknown"]
    assert "bogus" not in u["plot"] and "zzz" not in u["plot"]["figure"] and "extra" not in u
    assert "nope" not in u["series"][0] and u["series"][0]["id"] == "s5"
    sh = res["shape"]
    assert sh["plot"] == d["plot"] and sh["axes"] == d["axes"] and sh["save"]["dpi"] == d["save"]["dpi"]
    assert sh["load"]["files"] == [] and sh["annotations"] == [] and sh["fits"] == [] and sh["computed"] == []
    assert len(sh["series"]) == 1 and sh["series"][0] == d["series"][0]
    assert res["emptySeries"]["series"] == d["series"]
    dup = res["dups"]
    assert [s["id"] for s in dup["series"]] == ["s2", "s3", "s4"]
    assert [a["id"] for a in dup["annotations"]] == ["a2", "a1", "a3"] or len({a["id"] for a in dup["annotations"]}) == 3
    assert len({f["id"] for f in dup["fits"]}) == 2 and all(f["id"].startswith("f") for f in dup["fits"])
    assert [c["id"] for c in dup["computed"]] == ["c5", "c4", "c6"] or len({c["id"] for c in dup["computed"]}) == 3
    assert dup["computed"][1]["id"] == "c4"
    p = res["panels"]["plot"]["panels"]
    assert p == [
        {"title": "a", "xLabel": "", "yLabel": "", "y2Label": ""},
        {"title": "", "xLabel": "", "yLabel": "", "y2Label": ""},
        {"title": "", "xLabel": "x", "yLabel": "", "y2Label": ""},
    ]
    sc = res["scalars"]
    assert sc["plot"]["fontSize"] is None and sc["plot"]["title"] == 12 and sc["axes"]["x"]["min"] == "1e"


@needs_node
def test_ids_are_limited_to_safe_form(tmp_path):
    # id は画面の要素の id と HTML に入るので、「prefix + 数字」以外は振り直す。近似曲線の系列の参照も追従する
    res = node_io(
        tmp_path,
        """
        const evil = '"><img src=x onerror=alert(1)>';
        const s = io.parseSettingsFile(JSON.stringify({
          series: [{id: "s3"}, {id: evil}, {id: "series 1"}, {id: 7}],
          annotations: [{id: evil}, {id: "a2"}],
          fits: [{id: evil, series: evil}, {id: "f1", series: "series 1"}, {id: "f2", series: "s3"}],
          computed: [{id: "c1x", expr: "[0]"}],
        })).settings;
        console.log(JSON.stringify(s));
        """,
    )
    assert [x["id"] for x in res["series"]] == ["s3", "s4", "s5", "s6"]
    assert [x["id"] for x in res["annotations"]] == ["a3", "a2"]
    assert [x["id"] for x in res["fits"]] == ["f3", "f1", "f2"]
    assert [x["series"] for x in res["fits"]] == ["s4", "s5", "s3"]
    assert [x["id"] for x in res["computed"]] == ["c1"]


@needs_node
def test_migration_rules(tmp_path):
    res = node_io(
        tmp_path,
        """
        const parse = (o) => io.parseSettingsFile(JSON.stringify(o)).settings;
        console.log(JSON.stringify({
          v1: parse({version: 1, plot: {}}),
          v1dpi: parse({version: 1, save: {dpi: 200}, plot: {}}),
          v2: parse({version: 2, plot: {}, load: {parseDates: true}}),
          v2missing: parse({version: 2, plot: {}}),
          v3: parse({version: 3, plot: {}}),
          none: parse({plot: {}}),
          v4: parse({version: 4, plot: {}}),
        }));
        """,
    )
    assert res["v1"]["save"]["dpi"] == 120 and res["v1"]["load"]["parseDates"] is False and res["v1"]["version"] == 4
    assert res["v1dpi"]["save"]["dpi"] == 200
    assert res["v2"]["load"]["parseDates"] is True and res["v2missing"]["load"]["parseDates"] is False
    assert res["v3"]["load"]["parseDates"] is True and res["v3"]["save"]["dpi"] == 300
    assert res["none"]["version"] == 4 and res["none"]["load"]["parseDates"] is True and res["v4"]["save"]["dpi"] == 300


@needs_node
def test_map_positional_sources(tmp_path):
    res = node_io(
        tmp_path,
        """
        const s = clone(DEFAULT_SETTINGS);
        const mk = (id, source) => ({...clone(DEFAULT_SERIES), id, source, x: "__idx__1", y: "__idx__2"});
        s.series = [mk("s1", "d1"), mk("s2", "d2"), mk("s3", "d3"), mk("s4", "")];
        s.computed = [{id: "c1", source: "d2", name: "", expr: "[0]"}, {id: "c2", source: "d3", name: "", expr: "[0]"}, {id: "c3", source: "", name: "", expr: "[0]"}];
        s.plot.xColumn = "__idx__4";
        const two = io.mapPositionalSources(s, ["d5", "d9"]);
        const none = io.mapPositionalSources(s, []);
        const first = clone(s); first.series[0].source = "d3"; first.series[0].errorBars.y.column = "__idx__3";
        const lost = io.mapPositionalSources(first, ["d5", "d9"]);
        console.log(JSON.stringify({two, none, lost}));
        """,
    )
    two = res["two"]
    assert [s["source"] for s in two["settings"]["series"]] == ["d5", "d9", "", ""]
    assert two["settings"]["series"][2]["x"] == "" and two["settings"]["series"][2]["y"] == ""
    assert two["settings"]["series"][1]["x"] == "__idx__1"
    assert [c["source"] for c in two["settings"]["computed"]] == ["d9", "", ""]
    assert two["notes"] == [
        "系列3: 設定のデータ3に当たるファイルが無いため、データ元をデータ1に戻し、列を自動に戻しました。",
        "計算した列2: 設定のデータ3に当たるファイルが無いため、データ元を先頭のファイルに戻しました。",
    ]
    assert two["settings"]["plot"]["xColumn"] == "__idx__4"  # 系列1が見つかるので触らない
    assert [s["source"] for s in res["none"]["settings"]["series"]] == ["d1", "d2", "d3", ""] and res["none"]["notes"] == []
    lost = res["lost"]
    assert lost["settings"]["plot"]["xColumn"] == "" and lost["settings"]["series"][0]["errorBars"]["y"]["column"] == ""


@needs_node
def test_replace_settings_counters(tmp_path):
    script = """
    import { addSeries, addAnnotation, addFit, addComputed, replaceSettings, getSettings, subscribe, setLastPreset, getLastPreset } from "./state.js";
    import { DEFAULT_SETTINGS, DEFAULT_SERIES } from "./defaults.js";
    const clone = (v) => JSON.parse(JSON.stringify(v));
    const events = [];
    subscribe((_s, c) => events.push(c));
    const next = clone(DEFAULT_SETTINGS);
    next.series = [{...clone(DEFAULT_SERIES), id: "s4"}, {...clone(DEFAULT_SERIES), id: "s9"}];
    next.annotations = [{id: "a3", kind: "hline"}];
    next.fits = [{id: "f7", series: "s4"}];
    next.computed = [{id: "c2", source: "", name: "", expr: "[0]"}];
    next.plot.title = "replaced";
    setLastPreset({name: "p"});
    replaceSettings(next);
    const ids = {series: addSeries().id, ann: addAnnotation().id, fit: addFit().id, comp: addComputed().id};
    next.plot.title = "mutated after";  // 入れ替えた設定は渡した object と共有しない
    console.log(JSON.stringify({events, ids, title: getSettings().plot.title, preset: getLastPreset(), n: getSettings().series.length}));
    """
    res = run_node(tmp_path, STATE_FILES, script)
    assert res["events"][0] == {"kind": "settings-replaced", "origin": "user"}
    assert res["ids"] == {"series": "s10", "ann": "a4", "fit": "f8", "comp": "c3"}
    assert res["title"] == "replaced" and res["preset"] is None and res["n"] == 3


# ---- Python との一致 ----

SAMPLES = {
    "v4_default": {"version": 4, "plot": {}},
    "v4_partial": {
        "version": 4,
        "plot": {"title": "T", "type": "scatter", "figure": {"width": 10}, "layout": {"rows": 2}},
        "series": [{"id": "s1", "y": "__idx__1", "color": "#005AFF", "errorBars": {"y": {"mode": "fixed", "value": 1}}}, {"id": "s2", "y": "__idx__2", "panel": 1}],
        "annotations": [{"id": "a1", "kind": "vline", "x": "3"}],
        "fits": [{"id": "f1", "series": "s1", "model": "poly"}],
        "computed": [{"id": "c1", "name": "n", "expr": "[1] * 2"}],
        "axes": {"x": {"label": "X", "min": 1}},
    },
    "v3": {"version": 3, "plot": {"fontSize": 12}, "axes": {"y": {"scale": "log"}}, "save": {"dpi": 150}},
    "v2": {"version": 2, "plot": {"title": "v2"}, "load": {"skipLines": 2}, "series": [{"y": "__idx__1"}]},
    "v2_dates": {"version": 2, "load": {"parseDates": True}, "plot": {}},
    "v1": {"version": 1, "plot": {"type": "bar"}, "series": [{"y": "__idx__1", "label": "a"}]},
    "v1_dpi": {"version": 1, "save": {"dpi": 200, "format": "svg"}},
    "no_version": {"plot": {"title": "x"}, "series": [{"id": "s1"}]},
    "panels": {"plot": {"layout": {"rows": 2, "cols": 2}, "panels": [{"title": "a"}, {"xLabel": "x"}]}, "series": [{"id": "s1", "panel": 3}]},
    "custom_fit": {"fits": [{"id": "f1", "series": "s1", "model": "custom", "expr": "a*x+b", "initial": {"a": 2}}]},
}


@needs_node
@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_normalized_settings_parse_like_raw(tmp_path, name):
    raw = SAMPLES[name]
    script = f"""
    import * as io from "./settings-io.js";
    const raw = {json.dumps(raw)};
    console.log(JSON.stringify(io.parseSettingsFile(JSON.stringify(raw)).settings));
    """
    normalized = run_node(tmp_path, IO_FILES, script)
    assert parse_settings(normalized) == parse_settings(raw)


@needs_node
def test_normalized_default_equals_python_default(tmp_path):
    script = """
    import * as io from "./settings-io.js";
    console.log(JSON.stringify(io.parseSettingsFile(JSON.stringify({version: 4, plot: {}})).settings));
    """
    assert run_node(tmp_path, IO_FILES, script) == default_settings()


FILENAME_CASES = [
    "", "   ", "plot", "figure1", "figure.png", "a.b.c", "a.b.", "...", ".hidden", ".png", "x..", " name ", "a/b\\c", 'a:b*c?d"e<f>g|h',
    "日本語.png", "日本語の図", "with space.txt", "tab\there", "ctrl\x01char.x", "\x85pad\x85", "　全角　", "﻿bom", "a. ", ". .", "a. ", "ab .png",
    "con.json", "\x1fa\x1f", "x.tar.gz", "名前.", "/", ":::", "..png",
]


@needs_node
def test_settings_filename_matches_build_filename(tmp_path):
    script = f"""
    import {{ settingsFilename }} from "./settings-io.js";
    console.log(JSON.stringify({json.dumps(FILENAME_CASES)}.map(settingsFilename)));
    """
    out = run_node(tmp_path, IO_FILES, script)
    for raw, got in zip(FILENAME_CASES, out):
        expected = build_filename(raw, "json")[: -len(".json")] + "_settings.json"
        assert got == expected, repr(raw)
    assert out[0] == "plot_settings.json" and out[3] == "figure1_settings.json"
