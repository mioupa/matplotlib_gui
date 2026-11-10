"""デフォルト設定の生成コードが変わっていないことを確かめるための、代表的な構成（golden ファイルの元）。"""
from __future__ import annotations

from pathlib import Path

from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot
from mplgui.loader import load_file
from mplgui.settings import default_settings, parse_settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name):
    return load_file((FIXTURES / name).read_bytes(), name, "", True)


def _build(files, mutate):
    raw = default_settings()
    mutate(raw)
    settings = parse_settings(raw)
    loaded = {f["id"]: _load(f["name"]) for f in raw["load"]["files"]}
    data = {k: v.df for k, v in loaded.items()}
    info = {k: v.source for k, v in loaded.items()}
    plan = plan_plot(data, settings)
    return generate_script(settings, info, plan).text


def _one(name, plot_type, series, extra=None):
    def mutate(raw):
        raw["load"]["files"] = [{"id": "d1", "name": name, "sheet": ""}]
        raw["plot"]["type"] = plot_type
        raw["series"] = series
        if extra:
            extra(raw)
    return mutate


def _two(raw):
    raw["load"]["files"] = [{"id": "d1", "name": "utf8.csv", "sheet": ""}, {"id": "d2", "name": "growth.csv", "sheet": ""}]
    raw["series"] = [
        {"id": "s1", "x": "__idx__0", "y": "__idx__1", "source": "d1"},
        {"id": "s2", "x": "__idx__0", "y": "__idx__2", "source": "d2", "color": "#005AFF"},
    ]


CASES = {
    "line": _one("utf8.csv", "line", [{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__2", "secondaryAxis": True}]),
    "scatter": _one("utf8.csv", "scatter", [{"x": "__idx__0", "y": "__idx__1"}], lambda r: r["plot"]["grid"].update(major=True, minor=True)),
    "bar_single": _one("categories.csv", "bar", [{"y": "__idx__1"}], lambda r: r["plot"].update(xColumn="__idx__0")),
    "bar_multi": _one("categories.csv", "bar", [{"y": "__idx__1"}, {"y": "__idx__2"}], lambda r: r["plot"].update(xColumn="__idx__0")),
    "datetime_line": _one("datetime.csv", "line", [{"x": "__idx__0", "y": "__idx__3"}]),
    "datetime_format": _one("datetime.csv", "line", [{"x": "__idx__0", "y": "__idx__3"}], lambda r: r["axes"]["x"].update(dateFormat="%m/%d")),
    "log_axes": _one("growth.csv", "line", [{"x": "__idx__0", "y": "__idx__1"}], lambda r: r["axes"]["y"].update(scale="log")),
    "bar_multi_index": _one("growth.csv", "bar", [{"y": "__idx__1"}, {"y": "__idx__2"}]),
    "text_x_line": _one("categories.csv", "line", [{"x": "__idx__0", "y": "__idx__1"}]),
    "two_files": _two,
}


def build(name):
    mutate = CASES[name]
    return _build(None, mutate)
