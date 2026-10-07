"""mplgui の各モジュールが js / pyodide / pyscript に依存せず CPython で import でき、基本動作することを確認する。"""
import ast
from pathlib import Path

import pytest

from mplgui.loader import decode_delimiter, load_dataframe
from mplgui.runner import build_filename, figure_to_data_uri

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PKG = Path(__file__).resolve().parents[2] / "py" / "mplgui"


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
                assert n.split(".")[0] not in {"js", "pyodide", "pyscript"}, f"{path.name} imports {n}"


def test_load_csv_and_delimiter():
    df = load_dataframe((FIXTURES / "utf8.csv").read_bytes(), "utf8.csv", "", True)
    assert not df.empty
    assert decode_delimiter("", ".csv") == ","
    assert decode_delimiter(r"\t", ".txt") == "\t"


def test_build_filename():
    assert build_filename("", "png") == "plot.png"
    assert build_filename("fig.1.svg", "pdf") == "fig.1.pdf"
    assert build_filename("name.", "jpg") == "name.jpg"


def test_figure_to_data_uri_png():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    uri, ext = figure_to_data_uri(fig, "png")
    plt.close(fig)
    assert uri.startswith("data:image/png;base64,") and ext == "png"
