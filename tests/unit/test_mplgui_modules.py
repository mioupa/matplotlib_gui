"""mplgui の各モジュールが js / pyodide / pyscript に依存せず CPython で import できること。"""
import ast
import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PKG = Path(__file__).resolve().parents[2] / "py" / "mplgui"
FORBIDDEN = {"js", "pyodide", "pyscript"}


def test_no_browser_imports():
    for path in PKG.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                assert n.split(".")[0] not in FORBIDDEN, f"{path.name} imports {n}"


def test_every_module_imports_on_cpython():
    for path in sorted(PKG.glob("*.py")):
        if path.name != "__init__.py":
            importlib.import_module(f"mplgui.{path.stem}")


def test_main_py_does_not_touch_the_dom():
    text = (PKG.parent / "main.py").read_text(encoding="utf-8")
    assert "document" not in text and "getElementById" not in text
