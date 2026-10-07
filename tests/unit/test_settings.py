import copy
import json

import pytest

from mplgui.errors import UserError
from mplgui.settings import (
    SCHEMA_VERSION,
    default_settings,
    parse_load_settings,
    parse_settings,
    to_legacy_dict,
)

pytestmark = pytest.mark.unit


def test_defaults_are_complete_and_parse():
    d = default_settings()
    assert d["version"] == SCHEMA_VERSION == 1
    assert set(d) == {"version", "load", "plot", "axes", "series", "save"}
    assert set(d["axes"]) == {"x", "y", "y2"}
    s = parse_settings(d)
    assert s.plot.type == "line" and s.plot.font_size == 15 and s.plot.figure.width == 8 and s.plot.figure.height == 6
    assert s.load.has_header is True and s.load.delimiter == ""
    assert len(s.series) == 1 and s.series[0].id == "s1" and s.series[0].color == "#FF4B00"
    assert s.save.format == "png" and s.save.transparent is False
    json.dumps(d)  # JSON 互換


def test_default_settings_returns_fresh_objects():
    a = default_settings()
    a["series"][0]["color"] = "#000000"
    assert default_settings()["series"][0]["color"] == "#FF4B00"


def test_missing_keys_are_filled_from_defaults():
    s = parse_settings({"version": 1, "plot": {"title": "  T  "}, "series": [{"y": "__idx__2"}]})
    assert s.plot.title == "T"  # 前後の空白は取り除く
    assert s.plot.font_size == 15 and s.plot.legend_location == "best"
    assert s.series[0].y == "__idx__2" and s.series[0].line_width == 2 and s.series[0].id == "s1"
    assert parse_settings({}).plot.type == "line"
    assert parse_settings(None).series[0].x == ""


def test_series_without_id_get_unique_ids():
    s = parse_settings({"series": [{}, {}, {"id": "s1"}]})
    assert len({x.id for x in s.series}) == 3


def test_numeric_strings_are_accepted():
    raw = default_settings()
    raw["plot"]["fontSize"] = "12.5"
    raw["plot"]["skipRows"] = "3"
    raw["plot"]["figure"] = {"width": " 7 ", "height": 5}
    raw["axes"]["x"]["min"] = "0"
    raw["axes"]["x"]["max"] = "10.5"
    raw["series"][0]["lineWidth"] = "1.5"
    raw["series"][0]["markerSize"] = "4"
    s = parse_settings(raw)
    assert s.plot.font_size == 12.5 and s.plot.skip_rows == 3
    assert s.plot.figure.width == 7.0
    assert (s.axes.x.min, s.axes.x.max) == (0.0, 10.5)
    assert s.series[0].line_width == 1.5 and s.series[0].marker_size == 4.0


def test_empty_numbers_mean_default_or_none():
    raw = default_settings()
    raw["plot"]["fontSize"] = None
    raw["plot"]["skipRows"] = ""
    raw["axes"]["y"]["min"] = ""
    raw["series"][0]["lineWidth"] = None
    s = parse_settings(raw)
    assert s.plot.font_size == 15 and s.plot.skip_rows == 0 and s.axes.y.min is None and s.series[0].line_width == 2


def _expect_error(mutator, *needles):
    raw = default_settings()
    mutator(raw)
    with pytest.raises(UserError) as info:
        parse_settings(raw)
    msg = info.value.message
    assert any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in msg), f"日本語でない: {msg}"
    assert msg.isascii() is False
    for needle in needles:
        assert needle in msg, f"{needle!r} が {msg!r} に含まれない"
    return info.value


@pytest.mark.parametrize(
    "mutator, needles",
    [
        (lambda r: r["plot"].__setitem__("fontSize", "abc"), ("フォントサイズ", "数値")),
        (lambda r: r["plot"].__setitem__("fontSize", 0), ("フォントサイズ", "0より大きい")),
        (lambda r: r["plot"].__setitem__("fontSize", "invalid"), ("フォントサイズ",)),
        (lambda r: r["plot"].__setitem__("fontSize", True), ("フォントサイズ",)),
        (lambda r: r["plot"].__setitem__("fontSize", float("nan")), ("フォントサイズ",)),
        (lambda r: r["plot"]["figure"].__setitem__("width", -1), ("図幅",)),
        (lambda r: r["plot"]["figure"].__setitem__("height", "x"), ("図高さ",)),
        (lambda r: r["plot"].__setitem__("skipRows", -1), ("除外する先頭行数", "0以上の整数")),
        (lambda r: r["plot"].__setitem__("skipRows", "1.5"), ("除外する先頭行数", "整数")),
        (lambda r: r["plot"].__setitem__("skipRows", "abc"), ("除外する先頭行数",)),
        (lambda r: r["plot"].__setitem__("type", "pie"), ("プロット種別",)),
        (lambda r: r["plot"]["legend"].__setitem__("location", "nowhere"), ("凡例位置",)),
        (lambda r: r["plot"]["margins"].__setitem__("left", 1.5), ("余白 左(left)", "0〜1")),
        (lambda r: r["plot"]["margins"].__setitem__("top", "zz"), ("余白 上(top)",)),
        (lambda r: r["plot"]["margins"].update(left=0.9, right=0.1), ("left < right",)),
        (lambda r: r["plot"]["margins"].update(bottom=0.9, top=0.1), ("bottom < top",)),
        (lambda r: r["axes"]["x"].__setitem__("min", "q"), ("X軸の最小値",)),
        (lambda r: r["axes"]["y"].__setitem__("max", "q"), ("Y軸の最大値",)),
        (lambda r: r["axes"]["x"].update(min=5, max=1), ("X軸の範囲",)),
        (lambda r: r["axes"]["y"].update(scale="log", min=0), ("Y軸", "対数")),
        (lambda r: r["axes"]["x"].__setitem__("scale", "sqrt"), ("X軸スケール",)),
        (lambda r: r["series"][0].__setitem__("lineWidth", -1), ("系列1の", "「線幅」", "0より大きい")),
        (lambda r: r["series"][0].__setitem__("markerSize", -3), ("系列1の", "「点サイズ」", "0以上")),
        (lambda r: r["series"][0].__setitem__("markerSize", "x"), ("「点サイズ」",)),
        (lambda r: r["series"][0].__setitem__("lineStyle", "wavy"), ("「線種」",)),
        (lambda r: r["series"][0].__setitem__("color", "notacolor"), ("「色」",)),
        (lambda r: r["series"][0].__setitem__("secondaryAxis", "yes"), ("「第2軸を使用」",)),
        (lambda r: r["series"].append({"lineWidth": "bad"}), ("系列2の", "「線幅」")),
        (lambda r: r.__setitem__("series", []), ("描画系列",)),
        (lambda r: r["save"].__setitem__("format", "gif"), ("保存形式",)),
        (lambda r: r["save"].__setitem__("transparent", "yes"), ("背景を透過",)),
        (lambda r: r["plot"].__setitem__("title", 5), ("タイトル",)),
    ],
)
def test_validation_messages_are_japanese_and_name_the_field(mutator, needles):
    _expect_error(mutator, *needles)


def test_y2_range_only_checked_when_secondary_axis_used():
    raw = default_settings()
    raw["axes"]["y2"].update(min=5, max=1)
    parse_settings(raw)  # 第2軸を使う系列が無ければ検証しない
    raw["series"][0]["secondaryAxis"] = True
    with pytest.raises(UserError) as info:
        parse_settings(raw)
    assert "第2Y軸の範囲" in info.value.message


def test_unknown_version_rejected():
    raw = default_settings()
    del raw["version"]
    parse_settings(raw)  # version 欠落は現行版として扱う
    for bad in (2, 0, "1", None, True):
        raw = default_settings()
        raw["version"] = bad
        with pytest.raises(UserError) as info:
            parse_settings(raw)
        assert "バージョン" in info.value.message
    with pytest.raises(UserError):
        parse_load_settings({"version": 99})


def test_marker_size_auto_and_backstop():
    s = parse_settings(default_settings()).series[0]
    assert s.marker_size is None
    assert s.effective_marker_size("line") == 0 and s.effective_marker_size("scatter") == 24
    raw = default_settings()
    raw["series"][0]["markerSize"] = 0
    zero = parse_settings(raw).series[0]
    assert zero.effective_marker_size("line") == 0
    assert zero.effective_marker_size("scatter") == 24  # scatter で 0 以下なら 24
    raw["series"][0]["markerSize"] = 7
    assert parse_settings(raw).series[0].effective_marker_size("scatter") == 7


def test_parse_load_settings_ignores_other_invalid_fields():
    raw = default_settings()
    raw["plot"]["fontSize"] = "bad"
    raw["load"].update(delimiter=";", hasHeader=False)
    load = parse_load_settings(raw)
    assert load.delimiter == ";" and load.has_header is False


def test_settings_are_frozen():
    s = parse_settings(default_settings())
    with pytest.raises(Exception):
        s.plot.title = "x"
    with pytest.raises(Exception):
        s.series[0].color = "#000000"


def test_to_legacy_dict_shape():
    raw = default_settings()
    raw["plot"].update(title="T", skipRows=2, xColumn="__idx__1")
    raw["plot"]["margins"]["left"] = 0.1
    raw["axes"]["x"].update(label="X", min=0, max=5)
    raw["series"][0].update(label="L", secondaryAxis=True, y="__idx__2")
    d = to_legacy_dict(parse_settings(raw))
    expected_keys = {
        "skip_rows", "plot_type", "title", "x_label", "y_label", "y2_label", "x_scale", "y_scale", "y2_scale",
        "x_min", "x_max", "y_min", "y_max", "y2_min", "y2_max", "show_major_grid", "show_minor_grid",
        "legend_location", "font_size", "fig_width", "fig_height", "subplot_margins", "subplot_left",
        "subplot_right", "subplot_bottom", "subplot_top", "x_column_request", "series_settings", "series_settings_error",
    }
    assert set(d) == expected_keys
    assert d["skip_rows"] == 2 and d["plot_type"] == "line" and d["title"] == "T" and d["x_label"] == "X"
    assert d["x_min"] == 0 and d["x_max"] == 5 and d["subplot_left"] == 0.1
    assert d["subplot_margins"] == {"left": 0.1, "right": None, "bottom": None, "top": None}
    assert d["x_column_request"] == "__idx__1" and d["font_size"] == 15 and d["fig_width"] == 8
    assert d["series_settings"] == [
        {
            "y_request": "__idx__2", "x_request": "", "color": "#FF4B00", "line_width": 2.0, "line_style": "solid",
            "marker_size": 0.0, "legend_name": "L", "use_secondary_axis": True,
        }
    ]
    json.dumps(d)


def test_parse_does_not_mutate_input():
    raw = default_settings()
    before = copy.deepcopy(raw)
    parse_settings(raw)
    assert raw == before
