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
    out.cycled = nextSeriesColor();                       // すべて使用済み → 系列数で循環
    out.cycledExpected = PALETTE[getSettings().series.length % PALETTE.length];
    console.log(JSON.stringify(out));
    """
    res = run_node(tmp_path, {"state.mjs": "js/state.js", "defaults.js": "js/defaults.js"}, script)
    assert res["first"] == "#FF4B00"
    assert res["second"] == "#03AF7A"
    assert res["allUsed"] == 11
    assert res["cycled"] == res["cycledExpected"]
