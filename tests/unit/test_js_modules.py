"""純粋な JS モジュールを node で検証する（node が無ければ skip）。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
REPO = Path(__file__).resolve().parents[2]
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")


def run_node(tmp_path, files: dict[str, str], script: str):
    """files: {コピー先ファイル名: リポジトリ内の相対パス}。ES module として実行して JSON を返す。"""
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    for name, rel in files.items():
        (tmp_path / name).write_text((REPO / rel).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "run.mjs").write_text(script, encoding="utf-8")
    out = subprocess.run(["node", "run.mjs"], cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


@needs_node
def test_encoding_display_names(tmp_path):
    script = """
    globalThis.document = { getElementById: () => null };
    import { encodingDisplayName } from "./fileInfo.mjs";
    console.log(JSON.stringify(["utf-8", "utf-8-sig", "cp932", "euc-jp", null].map(encodingDisplayName)));
    """
    # import は先頭で巻き上げられるため、document の定義は不要（関数内でのみ使う）
    res = run_node(tmp_path, {"fileInfo.mjs": "js/ui/fileInfo.js"}, script)
    assert res == ["UTF-8", "UTF-8（BOM付き）", "Shift_JIS（CP932）", "EUC-JP", "Excel"]


@needs_node
def test_new_series_color_is_first_unused_palette_color(tmp_path):
    script = """
    import { addSeries, getSettings, updateSeries, nextSeriesColor } from "./state.mjs";
    import { PALETTE } from "./defaults.js";
    const out = {};
    updateSeries("s1", { color: "#005AFF" });           // 先頭色が空く
    out.first = nextSeriesColor();                        // #FF4B00
    addSeries();
    out.second = nextSeriesColor();                       // #03AF7A（#FF4B00 #005AFF は使用済み）
    while (getSettings().series.length < PALETTE.length) addSeries();
    out.allUsed = new Set(getSettings().series.map((s) => s.color)).size;
    out.newSource = getSettings().series[getSettings().series.length - 1].source;  // v3: データ元は空
    out.version = getSettings().version;
    out.cycled = nextSeriesColor();                       // すべて使用済み → 系列数で循環
    out.cycledExpected = PALETTE[getSettings().series.length % PALETTE.length];
    console.log(JSON.stringify(out));
    """
    files = {"state.mjs": "js/state.js", "defaults.js": "js/defaults.js", "palettes.js": "js/palettes.js", "presets.js": "js/presets.js"}
    res = run_node(tmp_path, files, script)
    assert res["first"] == "#FF4B00"
    assert res["second"] == "#03AF7A"
    assert res["allUsed"] == 11
    assert res["newSource"] == "" and res["version"] == 3
    assert res["cycled"] == res["cycledExpected"]


@needs_node
def test_unit_conversion_keeps_physical_size_and_rounds(tmp_path):
    script = """
    import { convertLength } from "./units.js";
    const c = convertLength;
    console.log(JSON.stringify({
      inToCm: c(8, "in", "cm"), cmToMm: c(20.32, "cm", "mm"), inToMm: c(8, "in", "mm"),
      h: [c(6, "in", "cm"), c(15.24, "cm", "mm")],
      back: c(c(c(8, "in", "cm"), "cm", "mm"), "mm", "in"),
      cmRound: c(c(8.5, "cm", "in"), "in", "cm"), cmToIn: c(8.5, "cm", "in"),
      same: c(8.5, "cm", "cm"), blank: c(null, "in", "cm"), bad: c("invalid", "in", "cm"), str: c("abc", "cm", "mm"),
    }));
    """
    res = run_node(tmp_path, {"units.js": "js/units.js"}, script)
    assert res["inToCm"] == 20.32 and res["cmToMm"] == 203.2 and res["inToMm"] == 203.2
    assert res["h"] == [15.24, 152.4]
    assert res["back"] == 8
    assert res["cmToIn"] == 3.346 and res["cmRound"] == 8.5
    assert res["same"] == 8.5
    assert res["blank"] is None and res["bad"] == "invalid" and res["str"] == "abc"


@needs_node
def test_preset_marker_rules(tmp_path):
    script = """
    import { PRESETS, planPreset } from "./presets.js";
    const series = [{ id: "a", markerSize: null }, { id: "b", markerSize: 30 }];
    const patches = (preset, type, s = series) => planPreset(PRESETS[preset], type, s).series.map((x) => x.patch);
    console.log(JSON.stringify({
      lineAuto: patches("paper1", "line"),
      scatter: patches("paper1", "scatter"),
      standardLine: patches("standard", "line"),
      standardScatter: patches("standard", "scatter"),
      slide: planPreset(PRESETS.slide, "line", series),
      names: Object.keys(PRESETS),
    }));
    """
    res = run_node(tmp_path, {"presets.js": "js/presets.js"}, script)
    assert res["lineAuto"] == [{"lineWidth": 1}, {"lineWidth": 1, "markerSize": 9}]  # 自動の折れ線に点を出さない
    assert res["scatter"] == [{"lineWidth": 1, "markerSize": 9}, {"lineWidth": 1, "markerSize": 9}]
    assert res["standardLine"] == [{"lineWidth": 2, "markerSize": None}] * 2  # 標準は自動に戻す
    assert res["standardScatter"] == res["standardLine"]
    assert res["slide"]["figure"] == {"width": 24, "height": 13.5, "unit": "cm"}
    assert res["slide"]["fontSize"] == 18 and res["slide"]["series"][1]["patch"] == {"lineWidth": 2.5, "markerSize": 49}
    assert res["names"] == ["standard", "paper1", "paper2", "slide"]


@needs_node
def test_palettes_and_state_use_current_palette(tmp_path):
    script = """
    import { addSeries, applyPalette, getSettings, nextSeriesColor, setLastPreset, setPath, updateSeries } from "./state.js";
    import { PALETTES } from "./palettes.js";
    import { PALETTE } from "./defaults.js";
    import { PRESETS } from "./presets.js";
    const out = {};
    out.udSame = JSON.stringify(PALETTES.ud) === JSON.stringify(PALETTE);
    updateSeries("s1", { color: "#123456" });               // 個別に選んだ色
    addSeries();
    const colors = () => getSettings().series.map((s) => s.color);
    applyPalette("tab10");
    out.tab10 = colors(); out.palette = getSettings().plot.palette;
    out.next = nextSeriesColor();                            // 3 番目: #2CA02C
    addSeries();
    out.added = colors()[2];
    applyPalette("gray");
    out.gray = colors();
    // 系列数がパレットより多いと循環する
    while (getSettings().series.length < 7) addSeries();
    applyPalette("gray");
    out.cycled = colors();
    // プリセット適用後に追加した系列
    setLastPreset(PRESETS.paper1);
    out.afterPreset = addSeries();
    setPath("plot.type", "scatter");
    out.afterPresetScatter = addSeries();
    setLastPreset(PRESETS.standard);
    out.afterStandard = addSeries();
    console.log(JSON.stringify(out));
    """
    files = {
        "state.js": "js/state.js", "defaults.js": "js/defaults.js",
        "palettes.js": "js/palettes.js", "presets.js": "js/presets.js",
    }
    res = run_node(tmp_path, files, script)
    assert res["udSame"] is True
    assert res["tab10"] == ["#1F77B4", "#FF7F0E"] and res["palette"] == "tab10"
    assert res["next"] == "#2CA02C" and res["added"] == "#2CA02C"
    assert res["gray"] == ["#000000", "#404040", "#707070"]
    assert res["cycled"][:7] == ["#000000", "#404040", "#707070", "#909090", "#B0B0B0", "#000000", "#404040"]
    assert res["afterPreset"]["lineWidth"] == 1 and res["afterPreset"]["markerSize"] is None
    assert res["afterPresetScatter"]["lineWidth"] == 1 and res["afterPresetScatter"]["markerSize"] == 9
    assert res["afterStandard"]["lineWidth"] == 2 and res["afterStandard"]["markerSize"] is None


@needs_node
def test_add_series_without_preset_is_unchanged(tmp_path):
    script = """
    import { addSeries } from "./state.js";
    console.log(JSON.stringify(addSeries()));
    """
    files = {"state.js": "js/state.js", "defaults.js": "js/defaults.js", "palettes.js": "js/palettes.js", "presets.js": "js/presets.js"}
    res = run_node(tmp_path, files, script)
    assert res["lineWidth"] == 2 and res["markerSize"] is None and res["color"] == "#005AFF"
