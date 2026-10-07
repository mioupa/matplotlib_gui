"""js/defaults.js の DEFAULT_SETTINGS と mplgui.settings.default_settings() が一致すること（node が無ければ skip）。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mplgui.settings import default_settings

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
def test_js_and_python_defaults_match(tmp_path):
    module = tmp_path / "defaults.mjs"
    module.write_text((REPO / "js" / "defaults.js").read_text(encoding="utf-8"), encoding="utf-8")
    script = f"import {{ DEFAULT_SETTINGS }} from {json.dumps(module.as_uri())}; console.log(JSON.stringify(DEFAULT_SETTINGS));"
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True, timeout=30)
    assert json.loads(out.stdout) == default_settings()


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無い")
def test_js_palette_has_default_series_color(tmp_path):
    module = tmp_path / "defaults.mjs"
    module.write_text((REPO / "js" / "defaults.js").read_text(encoding="utf-8"), encoding="utf-8")
    script = f"import {{ PALETTE, DEFAULT_SERIES }} from {json.dumps(module.as_uri())}; console.log(JSON.stringify([PALETTE, DEFAULT_SERIES.color]));"
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True, timeout=30)
    palette, color = json.loads(out.stdout)
    assert len(palette) == 11 and palette[0] == color == default_settings()["series"][0]["color"]
