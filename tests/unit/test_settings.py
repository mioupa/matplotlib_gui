import copy
import json

import pytest

from mplgui.errors import UserError
from mplgui.settings import (
    SCHEMA_VERSION,
    default_settings,
    parse_load_settings,
    migrate_settings,
    parse_save_settings,
    parse_settings,
)

pytestmark = pytest.mark.unit


def test_defaults_are_complete_and_parse():
    d = default_settings()
    assert d["version"] == SCHEMA_VERSION == 2
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
    s = parse_settings({"version": 2, "plot": {"title": "  T  "}, "series": [{"y": "__idx__2"}]})
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
    for bad in (3, 0, "1", None, True, "2"):
        raw = default_settings()
        raw["version"] = bad
        with pytest.raises(UserError) as info:
            parse_settings(raw)
        assert "バージョン" in info.value.message
    with pytest.raises(UserError):
        parse_load_settings({"version": 99})
    with pytest.raises(UserError):
        parse_save_settings({"version": 99})


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


def test_parse_save_settings_ignores_other_invalid_fields():
    raw = default_settings()
    raw["plot"]["fontSize"] = "bad"
    raw["axes"]["x"].update(min=5, max=1)
    raw["save"].update(filename=" out ", format="SVG", transparent=True)
    save = parse_save_settings(raw)
    assert save.filename == "out" and save.format == "svg" and save.transparent is True
    assert parse_save_settings({}) == parse_settings(default_settings()).save
    raw["save"]["format"] = "bmp"
    with pytest.raises(UserError) as info:
        parse_save_settings(raw)
    assert info.value.field == "保存形式"


def test_settings_are_frozen():
    s = parse_settings(default_settings())
    with pytest.raises(Exception):
        s.plot.title = "x"
    with pytest.raises(Exception):
        s.series[0].color = "#000000"


def test_parse_does_not_mutate_input():
    raw = default_settings()
    before = copy.deepcopy(raw)
    parse_settings(raw)
    assert raw == before


# ---------------------------------------------------------------- Phase 3: schema version 2


def test_new_defaults():
    d = default_settings()
    assert d["plot"]["figure"] == {"width": 8, "height": 6, "unit": "in"}
    assert d["plot"]["latinFont"] == "default" and d["plot"]["palette"] == "ud"
    assert d["save"] == {"filename": "", "format": "png", "transparent": False, "dpi": 300, "svgText": "path"}
    s = parse_settings(d)
    assert s.plot.figure.unit == "in" and s.plot.latin_font == "default" and s.plot.palette == "ud"
    assert s.save.dpi == 300 and s.save.svg_text == "path"


def test_figure_inches_per_unit():
    raw = default_settings()
    for unit, w, h, win, hin in (("in", 8, 6, 8, 6), ("cm", 8.5, 5, 8.5 / 2.54, 5 / 2.54), ("mm", 85, 50, 85 / 25.4, 50 / 25.4)):
        raw["plot"]["figure"] = {"width": w, "height": h, "unit": unit}
        fig = parse_settings(raw).plot.figure
        assert fig.unit == unit and fig.width == w and fig.height == h  # 設定は選んだ単位の値のまま
        assert fig.width_in == pytest.approx(win) and fig.height_in == pytest.approx(hin)


@pytest.mark.parametrize(
    "unit,ok,bad,limit",
    [("in", 50, 50.5, "50"), ("cm", 127, 128, "127"), ("mm", 1270, 1271, "1270")],
)
def test_figure_limit_depends_on_unit(unit, ok, bad, limit):
    raw = default_settings()
    raw["plot"]["figure"] = {"width": ok, "height": ok, "unit": unit}
    parse_settings(raw)
    for key, label in (("width", "図幅"), ("height", "図高さ")):
        raw["plot"]["figure"] = {"width": 5, "height": 5, "unit": unit, key: bad}
        with pytest.raises(UserError) as info:
            parse_settings(raw)
        assert info.value.field == label
        assert f"「{label}」は{limit}以下の数値で入力してください（単位: {unit}）。" == info.value.message
    raw["plot"]["figure"] = {"width": 0, "height": 5, "unit": unit}
    with pytest.raises(UserError) as info:
        parse_settings(raw)
    assert "0より大きい" in info.value.message


@pytest.mark.parametrize(
    "mutator,field_name",
    [
        (lambda r: r["plot"]["figure"].__setitem__("unit", "ft"), "図のサイズの単位"),
        (lambda r: r["plot"].__setitem__("latinFont", "comic"), "欧文フォント"),
        (lambda r: r["plot"].__setitem__("palette", "rainbow"), "カラーパレット"),
        (lambda r: r["save"].__setitem__("svgText", "outline"), "SVG の文字"),
        (lambda r: r["save"].__setitem__("dpi", 49), "保存 DPI"),
        (lambda r: r["save"].__setitem__("dpi", 1201), "保存 DPI"),
        (lambda r: r["save"].__setitem__("dpi", 300.5), "保存 DPI"),
        (lambda r: r["save"].__setitem__("dpi", "abc"), "保存 DPI"),
        (lambda r: r["save"].__setitem__("dpi", True), "保存 DPI"),
    ],
)
def test_new_fields_reject_invalid_values(mutator, field_name):
    raw = default_settings()
    mutator(raw)
    with pytest.raises(UserError) as info:
        parse_settings(raw)
    assert info.value.field == field_name and field_name in info.value.message


def test_new_choices_accept_valid_values():
    raw = default_settings()
    for latin in ("default", "arimo", "tinos"):
        for palette in ("ud", "tab10", "gray"):
            raw["plot"].update(latinFont=latin, palette=palette)
            p = parse_settings(raw).plot
            assert p.latin_font == latin and p.palette == palette
    for mode in ("path", "text"):
        raw["save"]["svgText"] = mode
        assert parse_settings(raw).save.svg_text == mode


def test_dpi_accepts_int_integral_float_string_and_blank():
    raw = default_settings()
    for given, expected in ((50, 50), (1200, 1200), (150, 150), (300.0, 300), ("600", 600), (" 72 ", 72), ("", 300), (None, 300)):
        raw["save"]["dpi"] = given
        assert parse_settings(raw).save.dpi == expected
        assert parse_save_settings(raw).dpi == expected
    raw["save"]["dpi"] = 150.0
    assert isinstance(parse_save_settings(raw).dpi, int)
    assert parse_save_settings(raw).dpi == 150


def test_dpi_message():
    with pytest.raises(UserError) as info:
        parse_save_settings({"save": {"dpi": 10}})
    assert info.value.message == "「保存 DPI」は50〜1200の整数で入力してください。"


def _v1():
    raw = default_settings()
    raw["version"] = 1
    raw["plot"]["figure"] = {"width": 7, "height": 5}
    for key in ("latinFont", "palette"):
        del raw["plot"][key]
    raw["save"] = {"filename": "x", "format": "jpg", "transparent": False}
    return raw


def test_migrate_v1_to_v2():
    raw = _v1()
    before = copy.deepcopy(raw)
    out = migrate_settings(raw)
    assert raw == before  # 引数は変更しない
    assert out["version"] == 2 and out["save"]["dpi"] == 120  # v1 は 120 dpi で保存していた
    assert out["save"]["filename"] == "x"
    s = parse_settings(raw)
    assert s.version == 2 and s.save.dpi == 120 and s.save.format == "jpg"
    assert s.plot.figure.unit == "in" and s.plot.figure.width == 7
    assert s.plot.latin_font == "default" and s.plot.palette == "ud" and s.save.svg_text == "path"


def test_migrate_v1_keeps_an_existing_dpi_and_handles_missing_save():
    raw = _v1()
    raw["save"]["dpi"] = 200
    assert migrate_settings(raw)["save"]["dpi"] == 200
    raw = _v1()
    del raw["save"]
    assert migrate_settings(raw)["save"] == {"dpi": 120}


def test_migrate_v1_through_save_and_load_parsers():
    assert parse_save_settings(_v1()).dpi == 120
    assert parse_load_settings(_v1()).has_header is True


def test_migrate_v2_passthrough_and_unknown_versions():
    raw = default_settings()
    out = migrate_settings(raw)
    assert out == raw and out is not raw
    assert migrate_settings({}) == {}  # バージョンの欠落は現行版として扱う（何も足さない）
    for bad in (3, 0, "2", True, None):
        with pytest.raises(UserError) as info:
            migrate_settings({"version": bad})
        assert "バージョン" in info.value.message
