import ast
import contextlib
import io
import shutil
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.collections import PathCollection
from matplotlib.patches import Rectangle

from mplgui import codegen
from mplgui.codegen import comment_text, generate_script, literal
from mplgui.dataprep import plan_plot
from mplgui.fonts import SANS_SERIF_PRIORITY
from mplgui.loader import SourceInfo, load_file
from mplgui.runner import ScriptError, figure_summary, figure_to_bytes, run_script
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def data():
    t = np.arange(30, dtype=float)
    temp = np.sin(t / 4) * 10 + 20
    temp[[3, 7]] = np.nan
    return pd.DataFrame({
        "時間": t,
        "温度": temp,
        "電圧": t * 3.0 + 1,
        "区分": [f"区分{i % 6}" for i in range(30)],
        "整数": (np.arange(30) % 5),
    })


def S(y, **kw):
    d = {"x": "", "y": f"__idx__{y}"}
    d.update(kw)
    return d


class Built:
    """CSV に書いたデータから、スクリプトを作り、全体を実行 / 自動描画の2通りで図を作る。"""

    def __init__(self, tmp_path, df, mutator=None, series=None, name="measure.csv", **load_args):
        self.dir = tmp_path
        self.csv = name
        df.to_csv(tmp_path / name, index=False, encoding="utf-8")
        self.loaded = load_file((tmp_path / name).read_bytes(), name, "", load_args.get("has_header", True))
        raw = default_settings()
        if series is not None:
            raw["series"] = series
        if mutator:
            mutator(raw)
        self.settings = parse_settings(raw)
        self.plan = plan_plot(self.loaded.df, self.settings)
        self.script = generate_script(self.settings, self.loaded.source, self.plan)

    @contextlib.contextmanager
    def full(self):
        with run_script(self.script.text, cwd=self.dir) as run:
            yield run

    @contextlib.contextmanager
    def auto(self):
        with run_script(self.script.auto_render_text(), injected={"df": self.loaded.df}) as run:
            yield run

    def summaries(self):
        with self.full() as run:
            full = figure_summary(run.fig)
        with self.auto() as run:
            auto = figure_summary(run.fig)
        return full, auto


def lines(ax):
    return ax.get_lines()


def bars(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle)]


# ---------------------------------------------------------------- matrix: compiles, runs as a file, runs auto, agree

MATRIX = {
    "line default": (lambda s: None, [S(1, x="__idx__0")]),
    "line two series secondary": (lambda s: s["axes"]["y2"].update(label="右軸"), [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]),
    "line markers dashed": (lambda s: None, [S(1, markerSize=16, lineStyle="dashed", lineWidth=3.5, color="#005AFF")]),
    "line skip rows + x index + title": (lambda s: s["plot"].update(skipRows=2, title="タイトル"), [S(1)]),
    "line log y limits": (lambda s: (s["axes"]["y"].update(scale="log", min=1, max=100), s["axes"]["x"].update(min=2, max=10)), [S(2, x="__idx__0")]),
    "line log x / log y2": (lambda s: (s["axes"]["x"].update(scale="log"), s["axes"]["y2"].update(scale="log")), [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]),
    "line grid major": (lambda s: s["plot"]["grid"].update(major=True), [S(1, x="__idx__0")]),
    "line grid minor": (lambda s: s["plot"]["grid"].update(minor=True), [S(1, x="__idx__0")]),
    "line grid both secondary": (lambda s: s["plot"]["grid"].update(major=True, minor=True), [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]),
    "line legend upper left": (lambda s: s["plot"]["legend"].update(location="upper left"), [S(1, x="__idx__0", label="温度")]),
    "line legend none": (lambda s: s["plot"]["legend"].update(location="none"), [S(1, x="__idx__0")]),
    "line margins partial": (lambda s: s["plot"]["margins"].update(left=0.2, top=0.8), [S(1, x="__idx__0")]),
    "line margins all": (lambda s: s["plot"]["margins"].update(left=0.2, right=0.9, bottom=0.2, top=0.8), [S(1, x="__idx__0")]),
    "line labels and font": (lambda s: (s["plot"].update(fontSize=1.5, title="t"), s["axes"]["x"].update(label="X軸"), s["axes"]["y"].update(label="Y軸")), [S(1, x="__idx__0")]),
    "line y auto": (lambda s: None, [{"x": "", "y": ""}, {"x": "", "y": ""}]),
    "line figure size": (lambda s: s["plot"]["figure"].update(width=5, height=3), [S(1, x="__idx__0")]),
    "scatter": (lambda s: s["plot"].update(type="scatter"), [S(1, x="__idx__0"), S(2, x="__idx__0", markerSize=60)]),
    "scatter secondary": (lambda s: s["plot"].update(type="scatter"), [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]),
    "bar single numeric x": (lambda s: s["plot"].update(type="bar", xColumn="__idx__0"), [S(2)]),
    "bar single string x": (lambda s: s["plot"].update(type="bar", xColumn="__idx__3"), [S(2)]),
    "bar single x index": (lambda s: s["plot"].update(type="bar"), [S(2)]),
    "bar multi": (lambda s: s["plot"].update(type="bar", xColumn="__idx__3"), [S(1), S(2, color="#03AF7A")]),
    "bar multi secondary": (lambda s: s["plot"].update(type="bar", xColumn="__idx__3"), [S(1), S(2, secondaryAxis=True)]),
    "bar multi x index three": (lambda s: s["plot"].update(type="bar"), [S(1), S(2), S(4)]),
    "figure size cm": (lambda s: s["plot"]["figure"].update(width=8.5, height=6, unit="cm"), [S(1, x="__idx__0")]),
    "figure size mm secondary": (lambda s: s["plot"]["figure"].update(width=85, height=60, unit="mm"), [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)]),
    "latin arimo": (lambda s: s["plot"].update(latinFont="arimo", title="Title"), [S(1, x="__idx__0")]),
    "latin tinos bar": (lambda s: s["plot"].update(latinFont="tinos", type="bar"), [S(2)]),
    "save svg path": (lambda s: s["save"].update(format="svg"), [S(1, x="__idx__0")]),
    "save svg text": (lambda s: s["save"].update(format="svg", svgText="text"), [S(1, x="__idx__0")]),
    "save pdf cm arimo": (lambda s: (s["save"].update(format="pdf"), s["plot"].update(latinFont="arimo"), s["plot"]["figure"].update(unit="cm", width=8.5, height=6)), [S(1, x="__idx__0")]),
    "save jpg dpi 72": (lambda s: s["save"].update(format="jpg", dpi=72), [S(1, x="__idx__0")]),
    "string x line": (lambda s: None, [S(1, x="__idx__3")]),
}


@pytest.mark.parametrize("name", list(MATRIX))
def test_script_compiles_runs_and_agrees(tmp_path, data, name):
    mutator, series = MATRIX[name]
    b = Built(tmp_path, data.head(12) if name.startswith("bar") else data, mutator, series)
    compile(b.script.text, "plot.py", "exec")
    full, auto = b.summaries()
    assert full == auto
    assert list(tmp_path.glob("plot.*"))  # 全体を実行すると savefig まで進む
    assert b.script.auto_render_text().count("\n") == b.script.text.count("\n")  # 行番号が同じ


def test_auto_render_variant_drops_only_load_and_output(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"].update(skipRows=2), [S(1, x="__idx__0")])
    auto = b.script.auto_render_text()
    assert "read_csv" not in auto and "savefig" not in auto and "plt.show" not in auto and "DATA_FILE" not in auto
    assert "read_csv" in b.script.text and "plt.show()" in b.script.text
    assert "df = df.iloc[2:].reset_index(drop=True)" in auto
    with pytest.raises(ScriptError) as info:
        with run_script(auto):  # df を渡さなければ動かない
            pass
    assert isinstance(info.value.exc, NameError)


# ---------------------------------------------------------------- expected artists


def test_line_two_series_artists(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1, x="__idx__0", color="#005AFF"), S(2, x="__idx__0", color="#03AF7A")])
    with b.auto() as r:
        ax = r.fig.axes[0]
        assert len(r.fig.axes) == 1 and len(lines(ax)) == 2 and not ax.collections
        assert lines(ax)[0].get_color().lower() == "#005aff" and lines(ax)[0].get_linewidth() == 2
        assert lines(ax)[0].get_marker() in ("", "None", None)
        assert [t.get_text() for t in ax.get_legend().get_texts()] == ["温度 [1]", "電圧 [2]"]
        assert len(lines(ax)[0].get_xdata()) == 28  # NaN の2行は描かない


def test_line_marker_size(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1, markerSize=9)])
    with b.auto() as r:
        ln = lines(r.fig.axes[0])[0]
        assert ln.get_marker() == "o" and ln.get_markersize() == pytest.approx(3.0)
    assert "markersize=9.0 ** 0.5" in b.script.text


def test_scatter_artists(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"].update(type="scatter"), [S(1, x="__idx__0"), S(2, x="__idx__0", markerSize=50)])
    with b.auto() as r:
        ax = r.fig.axes[0]
        cols = [c for c in ax.collections if isinstance(c, PathCollection)]
        assert len(cols) == 2 and not lines(ax)
        assert cols[0].get_sizes()[0] == 24 and cols[1].get_sizes()[0] == 50


def test_bar_single_and_multi(tmp_path, data):
    b = Built(tmp_path, data.head(6), lambda s: s["plot"].update(type="bar", xColumn="__idx__0"), [S(2)])
    with b.auto() as r:
        assert len(bars(r.fig.axes[0])) == 6
    b = Built(tmp_path, data.head(5), lambda s: s["plot"].update(type="bar"), [S(2), S(4)])
    with b.auto() as r:
        assert len(bars(r.fig.axes[0])) == 10


def test_bar_multi_keeps_category_tick_labels(tmp_path, data):
    b = Built(tmp_path, data.head(8), lambda s: s["plot"].update(type="bar", xColumn="__idx__3"), [S(1), S(2)])
    with b.auto() as r:
        ax = r.fig.axes[0]
        assert [t.get_text() for t in ax.get_xticklabels()] == [f"区分{i % 6}" for i in range(8)]
        assert all(t.get_rotation() == 45 for t in ax.get_xticklabels())


def test_bar_multi_log_scale_still_keeps_tick_labels(tmp_path, data):
    b = Built(
        tmp_path, data.head(8),
        lambda s: (s["plot"].update(type="bar", xColumn="__idx__3"), s["axes"]["y"].update(scale="log", min=0.5, max=1000)),
        [S(2), S(4)],
    )
    with b.auto() as r:
        ax = r.fig.axes[0]
        assert ax.get_yscale() == "log" and len(ax.get_xticklabels()) == 8


def test_bar_multi_thins_many_categories(tmp_path):
    df = pd.DataFrame({"k": [f"c{i}" for i in range(60)], "a": range(60), "b": range(60)})
    b = Built(tmp_path, df, lambda s: s["plot"].update(type="bar", xColumn="__idx__0"), [S(1), S(2)])
    with b.auto() as r:
        assert len(r.fig.axes[0].get_xticklabels()) == 30  # 60 // 25 = 2 個おき


def test_secondary_axis(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["axes"]["y2"].update(label="右軸"),
              [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)])
    with b.auto() as r:
        assert len(r.fig.axes) == 2
        ax, ax2 = r.fig.axes
        assert len(lines(ax)) == 1 and len(lines(ax2)) == 1 and ax2.get_ylabel() == "右軸"
        assert [t.get_text() for t in ax.get_legend().get_texts()] == ["温度 [1]", "電圧 [2]"]
    assert b.script.text.index("ax2 = ax.twinx()") > b.script.text.index("# 系列2")  # 第2軸の系列の直前に作る


def test_no_second_axis_without_secondary_series(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1)])
    assert "twinx" not in b.script.text and "ax2" not in b.script.text
    with b.auto() as r:
        assert len(r.fig.axes) == 1


@pytest.mark.parametrize("loc, expected", [("best", ["温度 [1]"]), ("lower right", ["温度 [1]"]), ("none", None)])
def test_legend(tmp_path, data, loc, expected):
    b = Built(tmp_path, data, lambda s: s["plot"]["legend"].update(location=loc), [S(1, x="__idx__0")])
    with b.auto() as r:
        legend = r.fig.axes[0].get_legend()
        assert (None if legend is None else [t.get_text() for t in legend.get_texts()]) == expected


def test_grid(tmp_path, data):
    def grids(ax):
        return any(g.get_visible() for g in ax.get_xgridlines()), any(g.get_visible() for g in ax.get_ygridlines())

    for major, minor, expect_major, expect_minor in [(False, False, False, False), (True, False, True, False), (False, True, False, True), (True, True, True, True)]:
        b = Built(tmp_path, data, lambda s: s["plot"]["grid"].update(major=major, minor=minor), [S(1, x="__idx__0")])
        with b.auto() as r:
            ax = r.fig.axes[0]
            assert grids(ax)[0] is expect_major
            assert ax.xaxis.get_minor_ticks()[0].gridline.get_visible() is expect_minor if expect_minor else True
            if not expect_minor:
                assert not any(t.gridline.get_visible() for t in ax.xaxis.get_minor_ticks())


def test_scales_and_limits(tmp_path, data):
    def m(s):
        s["axes"]["y"].update(scale="log", min=0.5, max=100)
        s["axes"]["x"].update(min=2, max=10)

    b = Built(tmp_path, data, m, [S(2, x="__idx__0")])
    with b.auto() as r:
        ax = r.fig.axes[0]
        assert ax.get_yscale() == "log" and ax.get_xscale() == "linear"
        assert ax.get_ylim() == (0.5, 100) and ax.get_xlim() == (2, 10)
    assert 'set_xscale("linear")' not in b.script.text  # 既定の線形は書かない


def test_single_sided_limits(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["axes"]["y"].update(min=-5), [S(1, x="__idx__0")])
    assert "ax.set_ylim(bottom=-5.0)" in b.script.text
    with b.auto() as r:
        assert r.fig.axes[0].get_ylim()[0] == -5


def test_log_y2_limits(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["axes"]["y2"].update(scale="log", min=1, max=500),
              [S(1, x="__idx__0"), S(2, x="__idx__0", secondaryAxis=True)])
    with b.auto() as r:
        assert r.fig.axes[1].get_yscale() == "log" and r.fig.axes[1].get_ylim() == (1, 500)


def test_title_labels_font_and_size(tmp_path, data):
    def m(s):
        s["plot"].update(title="タイトル", fontSize=12)
        s["plot"]["figure"].update(width=5, height=3)
        s["axes"]["x"]["label"] = "X軸"
        s["axes"]["y"]["label"] = "Y軸"

    b = Built(tmp_path, data, m, [S(1, x="__idx__0")])
    with b.auto() as r:
        ax = r.fig.axes[0]
        assert tuple(r.fig.get_size_inches()) == (5.0, 3.0)
        assert ax.get_title() == "タイトル" and ax.title.get_fontsize() == 14
        assert ax.get_xlabel() == "X軸" and ax.get_ylabel() == "Y軸" and ax.xaxis.label.get_fontsize() == 12
        assert ax.get_legend().get_texts()[0].get_fontsize() == 11
        assert ax.xaxis.get_ticklabels()[0].get_fontsize() == 11
    assert "FONT_SIZE = 12.0" in b.script.text and "FONT_SIZE - 1" in b.script.text


def test_font_size_clamp_is_a_literal(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"].update(fontSize=1.5), [S(1, x="__idx__0")])
    assert "labelsize=1.0" in b.script.text and "fontsize=1.0" in b.script.text and "FONT_SIZE - 1" not in b.script.text


def test_default_labels_come_from_columns(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1, x="__idx__0")])
    with b.auto() as r:
        assert r.fig.axes[0].get_xlabel() == "時間" and r.fig.axes[0].get_ylabel() == "温度 [1]"
    b = Built(tmp_path, data, None, [S(1), S(2)])
    with b.auto() as r:
        assert r.fig.axes[0].get_xlabel() == "index" and r.fig.axes[0].get_ylabel() == "values"


def test_margins(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"]["margins"].update(left=0.2, right=0.9), [S(1)])
    with b.auto() as r:
        assert r.fig.subplotpars.left == pytest.approx(0.2) and r.fig.subplotpars.right == pytest.approx(0.9)
    assert "fig.tight_layout()" in b.script.text and "fig.subplots_adjust(left=0.2, right=0.9)" in b.script.text

    b = Built(tmp_path, data, lambda s: s["plot"]["margins"].update(left=0.2, right=0.9, bottom=0.1, top=0.95), [S(1)])
    assert "fig.tight_layout()" not in b.script.text and "fig.subplots_adjust(left=0.2, right=0.9, bottom=0.1, top=0.95)" in b.script.text
    with b.auto() as r:
        p = r.fig.subplotpars
        assert (p.left, p.right, p.bottom, p.top) == (0.2, 0.9, 0.1, 0.95)

    b = Built(tmp_path, data, None, [S(1)])
    assert "subplots_adjust" not in b.script.text


def test_skip_rows(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"].update(skipRows=3), [S(0)])
    with b.auto() as r:
        assert list(lines(r.fig.axes[0])[0].get_ydata()) == list(data["時間"][3:])
    assert "df.iloc[3:]" in b.script.text
    b = Built(tmp_path, data, None, [S(0)])
    assert ".iloc[0:]" not in b.script.text and "reset_index" not in b.script.text


def test_x_index_vs_column(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["plot"].update(skipRows=2), [S(2)])
    assert "pd.Series(df.index)" in b.script.text
    with b.auto() as r:
        assert list(lines(r.fig.axes[0])[0].get_xdata())[:2] == [0, 1]
    b = Built(tmp_path, data, None, [S(1, x="__idx__0")])
    assert "pd.Series(df.index)" not in b.script.text and "df.iloc[:, 0]" in b.script.text


def test_x_numeric_strings_are_converted_and_text_x_is_positional(tmp_path):
    df = pd.DataFrame({"x": ["1", "2", "3", "4"], "k": list("abcd"), "y": [1.0, 2.0, 3.0, 4.0]})
    b = Built(tmp_path, df, None, [S(2, x="__idx__0")])
    assert 'x = pd.to_numeric(df.iloc[:, 0], errors="coerce")' not in b.script.text  # CSV から読むと数値列になる
    b = Built(tmp_path, df.assign(x=["1", "2", "3", "x"]), None, [S(2, x="__idx__0")])
    assert 'x = pd.to_numeric(df.iloc[:, 0], errors="coerce")' in b.script.text
    b = Built(tmp_path, df, None, [S(2, x="__idx__1")])
    assert "set_xscale" not in b.script.text  # 文字列の X は、目盛にカテゴリの値が出る（Phase 4 で Phase 2 の方式をやめた）
    full, auto = b.summaries()
    assert full == auto
    assert full[0]["xticklabels"] == ["a", "b", "c", "d"]


def test_no_header_file(tmp_path):
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
    (tmp_path / "raw.csv").write_text("1,4\n2,5\n3,6\n", encoding="utf-8")
    loaded = load_file((tmp_path / "raw.csv").read_bytes(), "raw.csv", "", False)
    raw = default_settings()
    raw["series"] = [S(1, x="__idx__0")]
    settings = parse_settings(raw)
    script = generate_script(settings, loaded.source, plan_plot(loaded.df, settings))
    assert "header=None" in script.text and "column_{i}" in script.text
    with run_script(script.text, cwd=tmp_path) as r:
        assert list(lines(r.fig.axes[0])[0].get_ydata()) == [4, 5, 6]
        assert r.fig.axes[0].get_xlabel() == "column_0"


def test_save_section_uses_save_settings(tmp_path, data):
    def m(s):
        s["save"].update(filename="結果.csv", format="jpg")

    b = Built(tmp_path, data, m, [S(1)])
    assert 'fig.savefig("結果.jpg", dpi=300, facecolor="white")' in b.script.text
    b = Built(tmp_path, data, lambda s: s["save"].update(format="svg", transparent=True), [S(1)])
    assert 'fig.savefig("plot.svg", transparent=True)' in b.script.text
    b = Built(tmp_path, data, None, [S(1)])
    assert 'fig.savefig("plot.png", dpi=300)' in b.script.text and b.script.text.rstrip().endswith("plt.show()")


def test_font_list_comes_from_fonts_module(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1)])
    expected = "[" + ", ".join(literal(n) for n in SANS_SERIF_PRIORITY) + "]"
    assert f'plt.rcParams["font.sans-serif"] = {expected}' in b.script.text
    assert SANS_SERIF_PRIORITY[0] == "Noto Sans JP"


def test_script_only_imports_pandas_matplotlib_numpy(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1), S(2, secondaryAxis=True)])
    tree = ast.parse(b.script.text)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported == {"matplotlib", "numpy", "pandas"}
    assert "mplgui" not in b.script.text


def test_steps_cover_failure_prone_lines(tmp_path, data):
    b = Built(tmp_path, data, lambda s: (s["plot"]["margins"].update(left=0.1), s["axes"]["y"].update(scale="log", min=1)), [S(1, x="__idx__0")])
    text_lines = b.script.text.split("\n")

    def step_text(line):
        step = b.script.step_for_line(line)
        return step.message if step else None

    def line_of(snippet):
        return next(i + 1 for i, line in enumerate(text_lines) if snippet in line)

    assert step_text(line_of("ax.plot(")) == codegen.GENERIC_ERROR_MESSAGE
    assert step_text(line_of("ax.set_yscale")) == codegen.axis_error_message("Y")
    assert b.script.step_for_line(line_of("ax.set_yscale")).field == "Y軸の範囲"
    assert step_text(line_of("fig.tight_layout()")) == codegen.TIGHT_LAYOUT_ERROR
    assert b.script.step_for_line(line_of("fig.tight_layout()")).field == "余白"
    assert step_text(line_of("fig.subplots_adjust")) == codegen.MARGIN_ERROR
    assert step_text(line_of("import pandas")) is None and b.script.step_for_line(None) is None


def test_section_line_ranges(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1)])
    text_lines = b.script.text.split("\n")
    s, e = b.script.load_lines
    assert text_lines[s - 1].startswith("# ==== 1.") and text_lines[e].startswith("# ==== 2.") is False  # 空行を挟む
    assert "read_csv" in "\n".join(text_lines[s - 1:e])
    s, e = b.script.output_lines
    assert text_lines[s - 1].startswith("# ==== 8.") and "plt.show()" in text_lines[e - 1]


# ---------------------------------------------------------------- source kinds


def test_xlsx_load_section(tmp_path):
    pytest.importorskip("openpyxl")
    shutil.copy(FIXTURES / "multi_sheet.xlsx", tmp_path / "multi_sheet.xlsx")
    loaded = load_file((tmp_path / "multi_sheet.xlsx").read_bytes(), "multi_sheet.xlsx", "", True)
    assert loaded.source.kind == "xlsx" and loaded.source.sheet_name == "Sheet1" and loaded.encoding is None
    raw = default_settings()
    raw["series"] = [S(1, x="__idx__0")]
    settings = parse_settings(raw)
    script = generate_script(settings, loaded.source, plan_plot(loaded.df, settings))
    assert "pd.read_excel(\n    DATA_FILE,\n" in script.text and '    sheet_name="Sheet1",  # シート\n' in script.text and "openpyxl" in script.text
    with run_script(script.text, cwd=tmp_path) as r:
        assert len(lines(r.fig.axes[0])) == 1


# ---------------------------------------------------------------- load equivalence with loader.load_file

LOAD_CASES = [
    ("utf8.csv", ""), ("utf8_bom.csv", ""), ("cp932.csv", ""), ("euc_jp.csv", ""), ("tab.txt", ""),
    ("tab.txt", "\\t"), ("duplicate_columns.csv", ""), ("non_numeric.csv", ""), ("multi_sheet.xlsx", ""),
]


@pytest.mark.parametrize("has_header", [True, False])
@pytest.mark.parametrize("name, delimiter", LOAD_CASES)
def test_generated_load_section_matches_loader(tmp_path, name, delimiter, has_header):
    if name.endswith(".xlsx"):
        pytest.importorskip("openpyxl")
    shutil.copy(FIXTURES / name, tmp_path / name)
    loaded = load_file((FIXTURES / name).read_bytes(), name, delimiter, has_header)
    raw = default_settings()
    raw["series"] = [{"x": "", "y": ""}]
    settings = parse_settings(raw)
    try:
        plan = plan_plot(loaded.df, settings)
    except Exception:
        plan = plan_plot(loaded.df, parse_settings({**default_settings(), "series": [S(0)]}))
    script = generate_script(settings, loaded.source, plan)
    start, end = script.load_lines
    section = "import pandas as pd\n" + "\n".join(script.text.split("\n")[start - 1:end])
    namespace: dict = {}
    cwd = Path.cwd()
    import os

    os.chdir(tmp_path)
    try:
        exec(compile(section, "load.py", "exec"), namespace)
    finally:
        os.chdir(cwd)
    pd.testing.assert_frame_equal(namespace["df"], loaded.df)


# ---------------------------------------------------------------- security

HOSTILE = [
    'a"\n__import__("os").system("echo hacked")\n#',
    "x\nraise SystemExit",
    "'''\nimport os; os.system('echo hacked')\n'''",
    " raise SystemExit ",
    "a\\",
    "t\x0craise SystemExit\x0b\x85",
]


def _calls(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return names


@pytest.mark.parametrize("hostile", HOSTILE)
def test_untrusted_strings_cannot_inject_code(tmp_path, hostile):
    df = pd.DataFrame({hostile: [1.0, 2.0, 3.0], "v": [4.0, 5.0, 6.0]})
    name = "d.csv"
    df.to_csv(tmp_path / name, index=False)
    loaded = load_file((tmp_path / name).read_bytes(), name, "", True)

    def mut(s):
        s["plot"]["title"] = hostile
        s["axes"]["x"]["label"] = hostile
        s["axes"]["y"]["label"] = hostile
        s["save"]["filename"] = hostile
        s["plot"]["legend"]["location"] = "best"

    raw = default_settings()
    raw["series"] = [{"x": "__idx__0", "y": "__idx__1", "label": hostile}, {"x": "__idx__0", "y": "__idx__1", "label": hostile, "secondaryAxis": True}]
    mut(raw)
    settings = parse_settings(raw)
    plan = plan_plot(loaded.df, settings)
    source = SourceInfo(filename=hostile + ".csv", kind="csv", encoding="utf-8", separator=",", has_header=True)
    script = generate_script(settings, source, plan)

    tree = ast.parse(script.text)  # 文法として正しい
    assert not ({"__import__", "system", "exit", "eval", "exec", "open"} & _calls(tree))
    # 実行しても、注入されたコードは動かない
    with run_script(script.auto_render_text(), injected={"df": loaded.df}) as run:
        assert "hacked" not in run.output
        assert run.fig.axes[0].get_title() == hostile.strip()
    # 悪意のある文字列がコメントの中で行を壊していない（コメント内に改行が無い）
    for line in script.text.split("\n"):
        assert "\r" not in line and " " not in line and "\x0b" not in line and "\x0c" not in line and "\x85" not in line


def test_hostile_text_only_appears_inside_literals_and_comments():
    hostile = 'q"\nimport os\n'
    text = codegen.comment_text(hostile)
    assert "\n" not in text
    assert literal(hostile) == repr(hostile) and "\n" not in literal(hostile)
    assert literal("plain") == '"plain"' and literal("it's") == '"it\'s"' and literal('say "hi"') == "'say \"hi\"'"
    assert ast.literal_eval(literal("a\\")) == "a\\" and ast.literal_eval(literal("""a'b"c""")) == """a'b"c"""


def test_literal_accepts_only_plain_values():
    assert literal(None) == "None" and literal(True) == "True" and literal(3) == "3" and literal(2.5) == "2.5"
    assert literal("a'b") == '"a\'b"'
    for bad in (float("nan"), float("inf"), [1], (1,), {"a": 1}, b"x", object(), np.float64(1.0), np.int64(1)):
        with pytest.raises((TypeError, ValueError)):
            literal(bad)


def test_comment_text_replaces_line_breaks_and_control_chars():
    text = comment_text("a\nb\rc d e\x85f\x0bg\x0ch\x00i\x1bj\tk")
    assert text == "a b c d e f g h i j k"
    assert comment_text("温度 [1]") == "温度 [1]"


def test_legend_is_not_emitted_when_no_label_can_be_shown(tmp_path, data):
    series = [S(1, x="__idx__0", label="_hidden"), S(2, x="__idx__0", label="_also")]
    b = Built(tmp_path, data, None, series)
    assert "ax.legend(" not in b.script.text and "get_legend_handles_labels" not in b.script.text
    assert "凡例は表示しない" in b.script.text or "凡例に出せるラベルが無い" in b.script.text
    full, auto = b.summaries()
    assert full[0]["legend"] == [] and auto[0]["legend"] == []


def test_legend_is_kept_when_one_label_is_visible(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1, x="__idx__0", label="_hidden"), S(2, x="__idx__0", label="見える")])
    assert "ax.legend(" in b.script.text
    full, _ = b.summaries()
    assert full[0]["legend"] == ["見える"]


def test_series_blocks_are_separated_by_a_blank_line(tmp_path, data):
    for plot_type in ("line", "scatter"):
        b = Built(tmp_path, data, lambda s, t=plot_type: s["plot"].update(type=t), [S(1, x="__idx__0"), S(2, x="__idx__0")])
        lines_ = b.script.text.split("\n")
        i = next(n for n, line in enumerate(lines_) if line.startswith("# 系列2"))
        assert lines_[i - 1] == "" and lines_[i - 2] != ""


def test_comments_use_the_same_word_for_tick_marks(tmp_path, data):
    b = Built(tmp_path, data, None, [S(1, x="__idx__3")])
    assert "目盛は内向き" in b.script.text and "目盛り" not in b.script.text


# ---------------------------------------------------------------- Phase 3: figure size, latin fonts, save rc


@pytest.mark.parametrize(
    "unit,w,h,exp_w,exp_h",
    [("in", 8, 6, 8, 6), ("cm", 8.5, 6, 8.5 / 2.54, 6 / 2.54), ("mm", 85, 60, 85 / 25.4, 60 / 25.4)],
)
def test_figure_size_per_unit(tmp_path, data, unit, w, h, exp_w, exp_h):
    b = Built(tmp_path, data, lambda s: s["plot"]["figure"].update(width=w, height=h, unit=unit), [S(1)])
    with b.full() as run:
        assert tuple(run.fig.get_size_inches()) == pytest.approx((exp_w, exp_h))
        assert run.fig.dpi == 100
    with b.auto() as run:
        assert tuple(run.fig.get_size_inches()) == pytest.approx((exp_w, exp_h))
    # 設定の inch 換算と生成コードが一致する
    assert (b.settings.plot.figure.width_in, b.settings.plot.figure.height_in) == pytest.approx((exp_w, exp_h))


@pytest.mark.parametrize("unit,w,h", [("in", 8, 6), ("cm", 20.32, 15.24), ("mm", 203.2, 152.4)])
def test_round_metric_sizes_keep_exact_pixels(tmp_path, data, unit, w, h):
    """切りのよい cm / mm（= 8 × 6 inch）でも、保存した画像の画素数が欠けない（1 / 2.54 を掛けると 2399 px になる）。"""
    b = Built(tmp_path, data, lambda s: s["plot"]["figure"].update(width=w, height=h, unit=unit), [S(1)])
    with b.full() as run:
        png, _, _ = figure_to_bytes(run.fig, "png", dpi=300)
    assert struct.unpack(">II", png[16:24]) == (2400, 1800)


def test_figure_section_text_per_unit(tmp_path, data):
    def section3(mut):
        text = Built(tmp_path, data, mut, [S(1)]).script.text
        return text.split("# ==== 3. 図と軸 ====\n")[1].split("\n\n")[0]

    assert section3(None) == "fig, ax = plt.subplots(figsize=(8.0, 6.0), dpi=100)  # 幅 8.0 × 高さ 6.0 インチ"
    cm = section3(lambda s: s["plot"]["figure"].update(width=8.5, height=6, unit="cm"))
    assert cm == (
        "CM_PER_INCH = 2.54  # 1 インチ = 2.54 cm（figsize はインチで指定するので、cm の値をこれで割る）\n"
        "fig, ax = plt.subplots(figsize=(8.5 / CM_PER_INCH, 6.0 / CM_PER_INCH), dpi=100)  # 幅 8.5 cm × 高さ 6.0 cm"
    )
    mm = section3(lambda s: s["plot"]["figure"].update(width=85, height=60, unit="mm"))
    assert mm.startswith("MM_PER_INCH = 25.4  # 1 インチ = 25.4 mm") and "figsize=(85.0 / MM_PER_INCH, 60.0 / MM_PER_INCH)" in mm


@pytest.mark.parametrize(
    "fmt,dpi,expected",
    [
        ("png", 300, 'fig.savefig("plot.png", dpi=300)'),
        ("png", 150, 'fig.savefig("plot.png", dpi=150)'),
        ("jpg", 72, 'fig.savefig("plot.jpg", dpi=72, facecolor="white")'),
        ("svg", 300, 'fig.savefig("plot.svg")'),
        ("pdf", 300, 'fig.savefig("plot.pdf")'),
    ],
)
def test_savefig_line_dpi_only_for_raster(tmp_path, data, fmt, dpi, expected):
    b = Built(tmp_path, data, lambda s: s["save"].update(format=fmt, dpi=dpi), [S(1)])
    assert expected in b.script.text
    if fmt in ("png", "jpg"):
        assert f"解像度（{dpi} dpi）" in b.script.text
    else:
        assert "解像度" not in b.script.text


def test_savefig_rc_lines_only_for_pdf_and_svg(tmp_path, data):
    def text(fmt, **kw):
        return Built(tmp_path, data, lambda s: s["save"].update(format=fmt, **kw), [S(1)]).script.text

    assert "fonttype" not in text("png") and "fonttype" not in text("jpg")
    pdf = text("pdf")
    assert 'plt.rcParams["pdf.fonttype"] = 42  # PDF に文字をフォントとして埋め込む' in pdf
    assert "OpenType（CFF）" in pdf and pdf.index("fonttype") < pdf.index("fig.savefig")
    note = [ln for ln in pdf.splitlines() if "OpenType（CFF）" in ln or "42 を 3 にする" in ln]
    assert len(note) == 2 and all(ln.startswith("#") and len(ln) < 100 for ln in note)  # 注記は2行に分ける
    assert 'plt.rcParams["svg.fonttype"] = "path"  # SVG の文字を図形（パス）にする' in text("svg")
    assert 'plt.rcParams["svg.fonttype"] = "path"' in text("svg", svgText="path")
    assert 'plt.rcParams["svg.fonttype"] = "none"  # SVG の文字をテキストのまま残す' in text("svg", svgText="text")


def test_rc_lines_come_from_formats_module(tmp_path, data):
    from mplgui.formats import savefig_rc

    assert savefig_rc("pdf") == {"pdf.fonttype": 42}
    assert savefig_rc("svg", "path") == {"svg.fonttype": "path"} and savefig_rc("svg", "text") == {"svg.fonttype": "none"}
    assert savefig_rc("png") == {} and savefig_rc("jpg") == {}


def test_script_with_pdf_save_runs_and_embeds_truetype(tmp_path, data):
    b = Built(tmp_path, data, lambda s: s["save"].update(format="pdf"), [S(1)])
    with b.full():
        pass
    pdf = (tmp_path / "plot.pdf").read_bytes()
    assert b"/FontFile2" in pdf and b"/Type3" not in pdf


def test_latin_default_header_is_unchanged(tmp_path, data):
    text = Built(tmp_path, data, None, [S(1)]).script.text
    assert 'plt.rcParams["font.family"] = "sans-serif"' in text
    assert "font_manager" not in text and "mathtext" not in text


def test_latin_font_header(tmp_path, data):
    arimo = Built(tmp_path, data, lambda s: s["plot"].update(latinFont="arimo"), [S(1)]).script.text
    assert "from matplotlib import font_manager" in arimo
    assert "# 欧文フォント: Arimo（Arial 互換）。無ければ一覧の次のフォントを使い、どれも無ければ日本語フォントで書く" in arimo
    assert 'latin = [name for name in ["Arimo", "Arial", "Liberation Sans"] if name in installed][:1]' in arimo
    assert 'plt.rcParams["font.family"] = latin + ["sans-serif"]' in arimo
    assert 'plt.rcParams["font.family"] = "sans-serif"' not in arimo and "mathtext" not in arimo
    assert 'plt.rcParams["axes.unicode_minus"] = False' in arimo
    tinos = Built(tmp_path, data, lambda s: s["plot"].update(latinFont="tinos"), [S(1)]).script.text
    assert '["Tinos", "Times New Roman", "Liberation Serif"]' in tinos
    assert 'plt.rcParams["mathtext.fontset"] = "stix"' in tinos


def _hide_fonts(monkeypatch, names):
    from matplotlib import font_manager

    monkeypatch.setattr(font_manager.fontManager, "ttflist", [f for f in font_manager.fontManager.ttflist if f.name not in names])
    font_manager.fontManager._findfont_cached.cache_clear()


@pytest.mark.parametrize("kind", ["arimo", "tinos"])
def test_latin_font_missing_logs_no_findfont_noise(tmp_path, data, monkeypatch, capsys, caplog, kind):
    import logging

    from mplgui.fonts import LATIN_FONTS

    _hide_fonts(monkeypatch, set(LATIN_FONTS[kind].candidates))
    b = Built(tmp_path, data, lambda s: s["plot"].update(latinFont=kind, title="タイトル"), [S(1, x="__idx__0")])
    with caplog.at_level(logging.WARNING, logger="matplotlib"):
        with b.full() as run:
            run.fig.canvas.draw()
            assert plt_rc_family(run) == ["sans-serif"]
    out = capsys.readouterr()
    assert "findfont" not in out.err + out.out + caplog.text and run.output.count("findfont") == 0


def plt_rc_family(run):
    import matplotlib

    return list(matplotlib.rcParams["font.family"])


def test_latin_font_installed_is_used(tmp_path, data, monkeypatch):
    from matplotlib import font_manager

    dejavu = font_manager.findfont("DejaVu Sans")
    entry = font_manager.FontEntry(fname=dejavu, name="Arimo", style="normal", variant="normal", weight=400, stretch="normal", size="scalable")
    monkeypatch.setattr(font_manager.fontManager, "ttflist", [*font_manager.fontManager.ttflist, entry])
    font_manager.fontManager._findfont_cached.cache_clear()
    try:
        b = Built(tmp_path, data, lambda s: s["plot"].update(latinFont="arimo"), [S(1, x="__idx__0")])
        with b.full() as run:
            assert plt_rc_family(run) == ["Arimo", "sans-serif"]
            run.fig.canvas.draw()
    finally:
        monkeypatch.undo()
        font_manager.fontManager._findfont_cached.cache_clear()
