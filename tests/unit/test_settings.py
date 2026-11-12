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
    validate_date_range,
)

pytestmark = pytest.mark.unit


def test_defaults_are_complete_and_parse():
    d = default_settings()
    assert d["version"] == SCHEMA_VERSION == 4
    assert set(d) == {"version", "load", "plot", "axes", "series", "annotations", "fits", "save"}
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
    s = parse_settings({"version": 3, "plot": {"title": "  T  "}, "series": [{"y": "__idx__2"}]})
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
    for bad in (5, 0, "1", None, True, "2", "3", "4"):
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
    return _strip_v3(raw)


def _strip_v3(raw):
    """v3 で足した項目を取り除く（v1 / v2 の設定の形にする）。"""
    raw["load"] = {"delimiter": "", "hasHeader": True}
    del raw["axes"]["x"]["dateFormat"]
    for item in raw["series"]:
        del item["source"]
    return raw


def test_migrate_v1_to_v2():
    raw = _v1()
    before = copy.deepcopy(raw)
    out = migrate_settings(raw)
    assert raw == before  # 引数は変更しない
    assert out["version"] == 4 and out["save"]["dpi"] == 120 and out["load"]["parseDates"] is False  # v1 は 120 dpi で保存していた
    assert out["save"]["filename"] == "x"
    s = parse_settings(raw)
    assert s.version == 4 and s.save.dpi == 120 and s.save.format == "jpg" and s.load.parse_dates is False
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


def test_migrate_current_passthrough_and_unknown_versions():
    raw = default_settings()
    out = migrate_settings(raw)
    assert out == raw and out is not raw
    assert migrate_settings({}) == {}  # バージョンの欠落は現行版として扱う（何も足さない）
    for bad in (5, 0, "2", "3", "4", True, None):
        with pytest.raises(UserError) as info:
            migrate_settings({"version": bad})
        assert "バージョン" in info.value.message


# ---------------------------------------------------------------- Phase 4: schema version 3


def _load(**kw):
    raw = default_settings()
    raw["load"].update(kw)
    return raw


def _err(raw, parser=parse_settings):
    with pytest.raises(UserError) as info:
        parser(raw)
    return info.value


def test_v3_defaults():
    d = default_settings()
    assert d["load"] == {
        "delimiter": "", "hasHeader": True, "skipLines": 0, "thousands": "", "decimal": ".",
        "comment": "", "parseDates": True, "files": [],
    }
    assert d["axes"]["x"]["dateFormat"] == "" and "dateFormat" not in d["axes"]["y"] and "dateFormat" not in d["axes"]["y2"]
    assert d["series"][0]["source"] == ""
    s = parse_settings(d)
    assert s.load.skip_lines == 0 and s.load.thousands == "" and s.load.decimal == "." and s.load.comment == ""
    assert s.load.parse_dates is True and s.load.files == () and s.axes.x.date_format == "" and s.series[0].source == ""
    assert s.axes.y.date_format == "" and s.axes.y2.date_format == ""


def test_v3_valid_load_values():
    raw = _load(skipLines="3", thousands="'", decimal=",", comment="#", parseDates=False,
                files=[{"id": "d1", "name": "a.csv", "sheet": ""}, {"id": "d12", "name": "b.xlsx", "sheet": "S2"}])
    s = parse_load_settings(raw)
    assert s.skip_lines == 3 and s.thousands == "'" and s.decimal == "," and s.comment == "#" and s.parse_dates is False
    assert [(f.id, f.name, f.sheet) for f in s.files] == [("d1", "a.csv", ""), ("d12", "b.xlsx", "S2")]
    for t in ("", ",", ".", " ", "'"):
        assert parse_load_settings(_load(thousands=t, decimal="." if t != "." else ",")).thousands == t
    assert parse_load_settings(_load(skipLines=1_000_000)).skip_lines == 1_000_000
    assert parse_load_settings(_load(skipLines="")).skip_lines == 0


@pytest.mark.parametrize("parser", [parse_settings, parse_load_settings])
def test_v3_invalid_load_values(parser):
    label = "ヘッダより前に読み飛ばす行数"
    for bad in (-1, 1.5, "x"):
        e = _err(_load(skipLines=bad), parser)
        assert e.field == label and e.message == f"「{label}」は0以上の整数で入力してください。"
    assert _err(_load(skipLines=1_000_001), parser).field == label
    assert _err(_load(thousands="x"), parser).field == "桁区切り"
    assert _err(_load(decimal=";"), parser).field == "小数点"
    e = _err(_load(thousands=",", decimal=","), parser)
    assert e.field == "桁区切り" and e.message == "「桁区切り」と「小数点」に同じ記号は使えません。"
    assert _err(_load(comment="##"), parser).message == "「コメント記号」は1文字で指定してください（例: #）。"
    for bad in ('"', " ", "\t"):
        e = _err(_load(comment=bad), parser)
        assert e.field == "コメント記号" and e.message == "「コメント記号」に \" や空白は使えません。"
    e = _err(_load(comment=",", thousands=","), parser)
    assert e.message == "「コメント記号」に、桁区切り・小数点と同じ記号は使えません。" and e.field == "コメント記号"
    assert _err(_load(comment="."), parser).field == "コメント記号"  # 小数点の既定値と同じ
    assert _err(_load(comment=5), parser).field == "コメント記号"
    assert _err(_load(parseDates="yes"), parser).field == "日時の列を自動で認識する"


@pytest.mark.parametrize("parser", [parse_settings, parse_load_settings])
def test_v3_invalid_files(parser):
    assert _err(_load(files="d1"), parser).field == "読み込むファイル"
    assert _err(_load(files=["d1"]), parser).field == "読み込むファイル"
    for bad_id in ("x1", "d", "d12345", "D1", 1, None):
        assert _err(_load(files=[{"id": bad_id, "name": "a", "sheet": ""}]), parser).field == "読み込むファイル"
    dup = [{"id": "d1", "name": "a", "sheet": ""}, {"id": "d1", "name": "b", "sheet": ""}]
    assert _err(_load(files=dup), parser).field == "読み込むファイル"
    ten = [{"id": f"d{i}", "name": "a", "sheet": ""} for i in range(1, 11)]
    assert len(parse_load_settings(_load(files=ten)).files) == 10
    eleven = ten + [{"id": "d11", "name": "a", "sheet": ""}]
    assert _err(_load(files=eleven), parser).message == "読み込めるファイルは10個までです。"
    assert _err(_load(files=[{"id": "d1", "name": 1, "sheet": ""}]), parser).field == "ファイル名"


def test_v3_series_source():
    raw = _load(files=[{"id": "d1", "name": "a.csv", "sheet": ""}, {"id": "d2", "name": "b.csv", "sheet": ""}])
    raw["series"] = [{"y": "__idx__1", "source": "d2"}, {"y": "__idx__1"}]
    s = parse_settings(raw)
    assert [x.source for x in s.series] == ["d2", ""]
    raw["series"].append({"y": "__idx__1", "source": "d9"})
    e = _err(raw)
    assert e.message == "系列3のデータ元が見つかりません。データ元を選び直してください。" and e.field == "系列3のデータ元"
    raw = default_settings()
    raw["series"][0]["source"] = "d1"  # files が空
    assert _err(raw).field == "系列1のデータ元"
    raw["series"][0]["source"] = 3
    assert _err(raw).field == "データ元"


def test_v3_date_format():
    for ok in ("", "%Y/%m/%d", "%m月%d日", "%H:%M", "%Y-%m-%d %H:%M:%S"):
        raw = default_settings()
        raw["axes"]["x"]["dateFormat"] = ok
        assert parse_settings(raw).axes.x.date_format == ok
    msg = "「X軸の日時の書式」が正しくありません。%Y/%m/%d のように、% で始まる指定を含めてください。"
    for bad in ("Y/m/d", "%Y" + "x" * 64, 5, ["%Y"]):
        raw = default_settings()
        raw["axes"]["x"]["dateFormat"] = bad
        e = _err(raw)
        assert e.message == msg and e.field == "X軸の日時の書式", bad
    raw = default_settings()
    raw["axes"]["y"]["dateFormat"] = "bad"  # Y 軸には書式の項目が無い（無視される）
    assert parse_settings(raw).axes.y.date_format == ""


def test_migrate_v2_to_v3():
    raw = _strip_v3(default_settings())
    raw["version"] = 2
    before = copy.deepcopy(raw)
    out = migrate_settings(raw)
    assert raw == before  # 引数は変更しない
    assert out["version"] == 4 and out["load"]["parseDates"] is False
    s = parse_settings(raw)
    assert s.version == 4 and s.load.parse_dates is False and s.load.skip_lines == 0 and s.load.decimal == "."
    assert s.load.files == () and s.axes.x.date_format == "" and s.series[0].source == ""
    assert s.save.dpi == 300  # v2 の dpi はそのまま
    assert parse_load_settings(raw).parse_dates is False
    assert parse_save_settings(raw).dpi == 300


def test_migrate_v2_keeps_an_existing_parse_dates():
    raw = _strip_v3(default_settings())
    raw["version"] = 2
    raw["load"]["parseDates"] = True
    assert migrate_settings(raw)["load"]["parseDates"] is True
    raw = {"version": 2}
    assert migrate_settings(raw) == {"version": 4, "load": {"parseDates": False}}
    assert parse_settings({"version": 2}).load.parse_dates is False


def test_v1_migrates_through_to_v3():
    out = migrate_settings(_v1())
    assert out["version"] == 4 and out["save"]["dpi"] == 120 and out["load"]["parseDates"] is False


def test_v3_without_parse_dates_defaults_to_true():
    assert parse_settings({"version": 3}).load.parse_dates is True
    assert parse_settings({}).load.parse_dates is True
    raw = default_settings()
    del raw["load"]["parseDates"]
    assert migrate_settings(raw) == raw and parse_load_settings(raw).parse_dates is True


# ---------------------------------------------------------------- Phase 5a: schema version 4


def _with4(mutate):
    raw = default_settings()
    mutate(raw)
    return raw


def _err4(mutate):
    with pytest.raises(UserError) as info:
        parse_settings(_with4(mutate))
    return info.value


def test_v4_defaults():
    d = default_settings()
    for key in ("x", "y", "y2"):
        axis = d["axes"][key]
        assert axis["majorStep"] is None and axis["minorTicks"] == "auto" and axis["minorDivisions"] is None
        assert axis["tickFormat"] == "auto" and axis["tickDecimals"] == 1 and axis["inverted"] is False
    assert d["axes"]["x"]["majorStepUnit"] == "day" and d["axes"]["x"]["dateMin"] == "" and d["axes"]["x"]["dateMax"] == ""
    assert "majorStepUnit" not in d["axes"]["y"] and "dateMin" not in d["axes"]["y2"]
    assert d["plot"]["spines"] == {"top": True, "right": True}
    eb = d["series"][0]["errorBars"]
    assert eb["capSize"] == 3
    for k in ("y", "x"):
        assert eb[k] == {"mode": "none", "symmetric": True, "value": None, "valueMinus": None, "column": "", "columnMinus": ""}
    assert eb["y"] is not eb["x"]
    s = parse_settings(d)
    assert s.axes.x.major_step is None and s.axes.x.major_step_unit == "day" and s.axes.y2.tick_decimals == 1
    assert s.plot.spine_top is True and s.plot.spine_right is True
    assert s.series[0].error_bars.cap_size == 3.0 and s.series[0].error_bars.y.mode == "none"


def test_v4_series_do_not_share_defaults():
    a, b = default_settings(), default_settings()
    a["series"][0]["errorBars"]["y"]["mode"] = "fixed"
    assert b["series"][0]["errorBars"]["y"]["mode"] == "none"
    s = parse_settings({"series": [{"y": "__idx__1"}, {"y": "__idx__2"}]})
    assert s.series[0].error_bars is not None and s.series[1].error_bars.y.mode == "none"


@pytest.mark.parametrize("axis,name", [("x", "X"), ("y", "Y"), ("y2", "第2Y")])
def test_tick_fields_validation(axis, name):
    def sec(raw):
        raw["series"][0]["secondaryAxis"] = True  # y2 を使う（目盛の項目を検証する）

    cases = [
        ("majorStep", 0, f"{name}軸の主目盛の間隔"),
        ("majorStep", -1, f"{name}軸の主目盛の間隔"),
        ("majorStep", "abc", f"{name}軸の主目盛の間隔"),
        ("minorTicks", "yes", f"{name}軸の副目盛"),
        ("minorDivisions", 1, f"{name}軸の副目盛の分割数"),
        ("minorDivisions", 11, f"{name}軸の副目盛の分割数"),
        ("minorDivisions", 2.5, f"{name}軸の副目盛の分割数"),
        ("tickFormat", "hex", f"{name}軸の目盛の書式"),
        ("tickDecimals", -1, f"{name}軸の目盛の小数の桁数"),
        ("tickDecimals", 11, f"{name}軸の目盛の小数の桁数"),
        ("tickDecimals", 1.5, f"{name}軸の目盛の小数の桁数"),
        ("inverted", "true", f"{name}軸を反転"),
    ]
    for key, value, field_name in cases:
        def m(raw, key=key, value=value):
            sec(raw)
            raw["axes"][axis][key] = value
            # 入力欄が出ている状態にする（隠れた項目は検証しない）
            raw["axes"][axis].update({"minorDivisions": {"minorTicks": "on"}, "tickDecimals": {"tickFormat": "fixed"}}.get(key, {}))

        e = _err4(m)
        assert e.field == field_name and field_name in e.message, (key, value)


def test_tick_fields_accepted_values():
    def m(raw):
        a = raw["axes"]["x"]
        a.update(majorStep="0.5", minorTicks="on", minorDivisions="4", tickFormat="fixed", tickDecimals=3.0, inverted=True)
        raw["axes"]["y"].update(majorStep=2, minorDivisions=None, tickFormat="pow10")

    s = parse_settings(_with4(m))
    assert s.axes.x.major_step == 0.5 and s.axes.x.minor_divisions == 4 and s.axes.x.tick_decimals == 3
    assert s.axes.x.minor_ticks == "on" and s.axes.x.tick_format == "fixed" and s.axes.x.inverted is True
    assert s.axes.y.major_step == 2.0 and s.axes.y.tick_format == "pow10"
    blank = parse_settings(_with4(lambda r: r["axes"]["x"].update(majorStep="", minorDivisions="  ", tickDecimals="")))
    assert blank.axes.x.major_step is None and blank.axes.x.minor_divisions is None and blank.axes.x.tick_decimals == 1


def test_major_step_unit():
    assert _err4(lambda r: r["axes"]["x"].update(majorStepUnit="week")).field == "X軸の主目盛の単位"
    for unit in ("year", "month", "day", "hour", "minute", "second"):
        assert parse_settings(_with4(lambda r, u=unit: r["axes"]["x"].update(majorStepUnit=u))).axes.x.major_step_unit == unit


def test_hidden_tick_fields_are_not_validated():
    """隠れている項目（副目盛が表示でないときの分割数、書式が小数・指数でないときの桁数、対数軸の間隔）は検証せず既定値にする。"""

    def m(raw):
        raw["axes"]["y"].update(scale="log", majorStep=-1, minorTicks="auto", minorDivisions=99, tickFormat="pow10", tickDecimals=99)

    s = parse_settings(_with4(m))
    y = s.axes.y
    assert y.major_step is None and y.minor_divisions is None and y.tick_decimals == 1
    # 表示されるようにすれば検証される
    for key, value, extra in (
        ("minorDivisions", 99, {"minorTicks": "on"}),
        ("tickDecimals", 99, {"tickFormat": "sci"}),
        ("majorStep", -1, {"scale": "linear"}),
    ):
        e = _err4(lambda r, k=key, v=value, x=extra: r["axes"]["y"].update({k: v, **x}))
        assert e.field.startswith("Y軸")
    kept = parse_settings(_with4(lambda r: r["axes"]["y"].update(minorTicks="on", minorDivisions="3", tickFormat="sci", tickDecimals=2)))
    assert kept.axes.y.minor_divisions == 3 and kept.axes.y.tick_decimals == 2


def test_y2_tick_fields_are_ignored_without_a_secondary_axis():
    def bad(raw):
        raw["axes"]["y2"].update(majorStep=-3, minorTicks="zzz", tickFormat="zzz", tickDecimals=99, inverted="x")

    s = parse_settings(_with4(bad))  # 第2Y軸を使っていないので、隠れた不正な値は無視する
    assert s.axes.y2.major_step is None and s.axes.y2.minor_ticks == "auto" and s.axes.y2.inverted is False
    e = _err4(lambda r: (bad(r), r["series"][0].update(secondaryAxis=True)))
    assert e.field == "第2Y軸の主目盛の間隔"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-01-31", "2026-01-31"),
        ("2026/01/31", "2026-01-31"),
        ("2026-1-5", "2026-01-05"),
        (" 2026-01-31 ", "2026-01-31"),
        ("2026-01-31 12:00", "2026-01-31 12:00:00"),
        ("2026-01-31T12:00", "2026-01-31 12:00:00"),
        ("2026/1/31 9:05:07", "2026-01-31 09:05:07"),
        ("2026-01-31 12:00:30", "2026-01-31 12:00:30"),
        ("", ""),
        (None, ""),
        ("   ", ""),
    ],
)
def test_date_range_is_normalized(text, expected):
    s = parse_settings(_with4(lambda r: r["axes"]["x"].update(dateMin=text)))
    assert s.axes.x.date_min == expected and s.axes.x.date_max == ""


@pytest.mark.parametrize("text", ["31-01-2026", "2026-13-01", "2026-02-30", "2026-01-31 25:00", "2026-01-31 12", "2026-01/31", "abc", "2026", "2026-01-31 12:00:60", 20260131])
def test_date_range_rejects_bad_forms(text):
    # settings は描画を止めない（X が日時でなければ使わない）。検証は X が日時のとき（validate_date_range）
    s = parse_settings(_with4(lambda r: r["axes"]["x"].update(dateMax=text)))
    assert s.axes.x.date_max == (text.strip() if isinstance(text, str) else str(text))
    with pytest.raises(UserError) as info:
        validate_date_range(s.axes.x)
    e = info.value
    assert e.field == "X軸の範囲（日時）" and "2026-01-31 または 2026-01-31 12:00" in e.message


def test_date_range_min_must_be_before_max():
    ok = parse_settings(_with4(lambda r: r["axes"]["x"].update(dateMin="2026-01-01", dateMax="2026-01-01 00:00:01")))
    assert ok.axes.x.date_min < ok.axes.x.date_max
    assert validate_date_range(ok.axes.x) == ("2026-01-01", "2026-01-01 00:00:01")
    for lo, hi in (("2026-01-02", "2026-01-01"), ("2026-01-01", "2026/01/01"), ("2026-01-01 00:00", "2026-01-01")):
        s = parse_settings(_with4(lambda r, lo=lo, hi=hi: r["axes"]["x"].update(dateMin=lo, dateMax=hi)))
        with pytest.raises(UserError) as info:
            validate_date_range(s.axes.x)
        e = info.value
        assert e.field == "X軸の範囲（日時）" and "最小値 < 最大値" in e.message


def test_spines():
    s = parse_settings(_with4(lambda r: r["plot"]["spines"].update(top=False, right=False)))
    assert s.plot.spine_top is False and s.plot.spine_right is False
    assert _err4(lambda r: r["plot"]["spines"].update(top="no")).field == "上の枠線"
    assert _err4(lambda r: r["plot"]["spines"].update(right=1)).field == "右の枠線"


def _eb(**kw):
    def m(raw):
        raw["series"][0]["errorBars"]["y"].update(kw)
    return m


def test_error_bars_fixed_symmetric_and_asymmetric():
    s = parse_settings(_with4(_eb(mode="fixed", value="0.5")))
    spec = s.series[0].error_bars.y
    assert spec.mode == "fixed" and spec.symmetric and spec.value == 0.5 and spec.value_minus is None
    s = parse_settings(_with4(_eb(mode="fixed", symmetric=False, value=1, valueMinus=0)))
    spec = s.series[0].error_bars.y
    assert not spec.symmetric and spec.value == 1.0 and spec.value_minus == 0.0


def test_error_bars_fixed_required_and_messages():
    e = _err4(_eb(mode="fixed"))
    assert e.message == "系列1の「Y誤差の値」を入力してください。" and e.field == "Y誤差の値"
    e = _err4(_eb(mode="fixed", symmetric=False, value=1))
    assert e.message == "系列1の「Y誤差（下）の値」を入力してください。" and e.field == "Y誤差（下）の値"
    e = _err4(_eb(mode="fixed", symmetric=False, valueMinus=1))
    assert e.field == "Y誤差（上）の値"
    e = _err4(_eb(mode="fixed", value=-1))
    assert e.field == "Y誤差の値" and "0以上" in e.message
    assert _err4(_eb(mode="fixed", value="abc")).field == "Y誤差の値"
    assert _err4(_eb(mode="fixed", value=float("inf"))).field == "Y誤差の値"


def test_error_bars_columns_accept_only_index_form():
    s = parse_settings(_with4(_eb(mode="column", column="__idx__3")))
    assert s.series[0].error_bars.y.column == "__idx__3"
    s = parse_settings(_with4(_eb(mode="column", symmetric=False, column="__idx__3", columnMinus="__idx__4")))
    assert s.series[0].error_bars.y.column_minus == "__idx__4"
    e = _err4(_eb(mode="column"))
    assert e.message == "系列1の「Y誤差の列」を選んでください。" and e.field == "Y誤差の列"
    e = _err4(_eb(mode="column", column="温度"))  # 列名は受け付けない
    assert e.field == "Y誤差の列" and "指定が正しくありません" in e.message
    for bad in ("__idx__", "__idx__x", "__idx__-1", "idx3"):
        assert _err4(_eb(mode="column", column=bad)).field == "Y誤差の列"
    e = _err4(_eb(mode="column", symmetric=False, column="__idx__1"))
    assert e.field == "Y誤差（下）の列"
    e = _err4(_eb(mode="column", symmetric=False, columnMinus="__idx__1"))
    assert e.field == "Y誤差（上）の列"


def test_error_bars_x_labels_and_owner():
    def m(raw):
        raw["series"] = [{"y": "__idx__1"}, {"y": "__idx__2"}]
        raw["series"][1]["errorBars"] = {"x": {"mode": "fixed", "symmetric": False, "value": 1}}

    e = _err4(m)
    assert e.message == "系列2の「X誤差（左）の値」を入力してください。" and e.field == "X誤差（左）の値"

    def m2(raw):
        raw["series"][0]["errorBars"] = {"x": {"mode": "column", "symmetric": False, "column": "__idx__1"}}

    assert _err4(m2).field == "X誤差（左）の列"
    assert _err4(lambda r: r["series"][0]["errorBars"]["x"].update(mode="bad")).field == "X誤差の方式"
    assert _err4(_eb(mode="bad")).field == "Y誤差の方式"


def test_error_bars_unused_fields_are_not_validated():
    # mode が none のときは、残りの項目が不正でも検証しない
    s = parse_settings(_with4(_eb(mode="none", value="abc", column="温度", symmetric="x")))
    assert s.series[0].error_bars.y.mode == "none"


def test_error_bars_x_spec_is_skipped_for_bar():
    def m(raw):
        raw["plot"]["type"] = "bar"
        raw["series"][0]["errorBars"]["x"].update(mode="column", column="温度")

    s = parse_settings(_with4(m))
    assert s.series[0].error_bars.x.mode == "none"  # 棒グラフでは X 方向を使わない
    assert _err4(lambda r: (m(r), r["plot"].update(type="line"))).field == "X誤差の列"


def test_error_bars_cap_size():
    assert parse_settings(_with4(lambda r: r["series"][0]["errorBars"].update(capSize="7.5"))).series[0].error_bars.cap_size == 7.5
    assert parse_settings(_with4(lambda r: r["series"][0]["errorBars"].update(capSize=0))).series[0].error_bars.cap_size == 0.0
    for bad in (-1, 51, "abc"):
        e = _err4(lambda r, b=bad: r["series"][0]["errorBars"].update(capSize=b))
        assert e.field == "エラーバーの端の長さ"


def test_migrate_v3_to_v4_and_older():
    v3 = default_settings()
    v3["version"] = 3
    for key in ("spines",):
        del v3["plot"][key]
    for a in ("x", "y", "y2"):
        for key in ("majorStep", "minorTicks", "minorDivisions", "tickFormat", "tickDecimals", "inverted"):
            del v3["axes"][a][key]
    for key in ("majorStepUnit", "dateMin", "dateMax"):
        del v3["axes"]["x"][key]
    del v3["series"][0]["errorBars"]
    v3["load"]["parseDates"] = False
    out = migrate_settings(v3)
    assert out["version"] == 4 and out["load"]["parseDates"] is False  # v3 の出力を保つ（parseDates はそのまま）
    assert "spines" not in out["plot"]  # 項目は足さない。既定値は parse が補う
    s = parse_settings(v3)
    assert s.version == 4 and s.plot.spine_top and s.axes.x.minor_ticks == "auto" and s.series[0].error_bars.y.mode == "none"
    assert v3["version"] == 3  # 引数は変更しない
    for old in (1, 2):
        out = migrate_settings({"version": old})
        assert out["version"] == 4 and out["load"]["parseDates"] is False
    assert migrate_settings({"version": 1})["save"]["dpi"] == 120
    for bad in (5, 0, "4"):
        with pytest.raises(UserError):
            migrate_settings({"version": bad})


# ---------------------------------------------------------------- Phase 5b: 系列のスタイル・注釈・近似曲線


def test_5b_defaults():
    d = default_settings()
    assert d["annotations"] == [] and d["fits"] == []
    assert d["series"][0]["marker"] == "auto" and d["series"][0]["alpha"] == 1
    assert d["series"][0]["fill"] == {"lower": "", "upper": "", "alpha": 0.25}
    s = parse_settings(d)
    assert s.annotations == () and s.fits == ()
    assert (s.series[0].marker, s.series[0].alpha, s.series[0].fill.enabled, s.series[0].fill.alpha) == ("auto", 1.0, False, 0.25)


def test_v3_settings_without_5b_keys_parse_with_defaults():
    s = parse_settings({"version": 3, "series": [{"y": "__idx__1"}]})
    assert s.series[0].marker == "auto" and s.annotations == () and s.fits == ()


def test_series_style_fields_are_validated_with_series_number():
    base = default_settings()

    def with_series(**kw):
        raw = copy.deepcopy(base)
        raw["series"] = [{"id": "s1"}, {"id": "s2", **kw}]
        return raw

    for kw, field_name in [
        ({"marker": "zzz"}, "系列2の点の形"),
        ({"alpha": 1.1}, "系列2の不透明度"),
        ({"alpha": -0.1}, "系列2の不透明度"),
        ({"fill": {"lower": "__idx__1", "upper": ""}}, "系列2の塗りつぶし帯"),
        ({"fill": {"lower": "", "upper": "__idx__1"}}, "系列2の塗りつぶし帯"),
        ({"fill": {"lower": "abc", "upper": "__idx__1"}}, "系列2の塗りつぶし帯"),
        ({"fill": {"lower": "__idx__1", "upper": "__idx__2", "alpha": 2}}, "系列2の塗りつぶし帯"),
    ]:
        with pytest.raises(UserError) as e:
            parse_settings(with_series(**kw))
        assert e.value.field == field_name, kw


def test_fill_alpha_is_hidden_when_no_band():
    s = parse_settings({"series": [{"fill": {"lower": "", "upper": "", "alpha": "oops"}}]})
    assert not s.series[0].fill.enabled


def test_scatter_marker_none_is_error_but_line_is_fine():
    parse_settings({"plot": {"type": "line"}, "series": [{"marker": "none"}]})
    with pytest.raises(UserError) as e:
        parse_settings({"plot": {"type": "scatter"}, "series": [{"marker": "none"}]})
    assert e.value.field == "系列1の点の形"


def test_bar_hides_marker_and_fill_but_keeps_alpha():
    s = parse_settings(
        {"plot": {"type": "bar"}, "series": [{"marker": "zzz", "fill": {"lower": "x", "upper": ""}, "alpha": 0.4}]}
    ).series[0]
    assert (s.marker, s.fill.enabled, s.alpha) == ("auto", False, 0.4)


def test_annotation_and_fit_elements_are_filled_from_defaults():
    s = parse_settings({"annotations": [{}], "fits": [{}]})
    a, f = s.annotations[0], s.fits[0]
    assert (a.id, a.kind, a.color, a.line_style, a.line_width, a.alpha, a.font_size) == ("a1", "hline", "#000000", "dashed", 1.0, None, None)
    assert (f.id, f.series, f.model, f.degree, f.show, f.color) == ("f1", "s1", "linear", 1, "legend", "")


def test_annotation_and_fit_lists_must_be_lists():
    for key in ("annotations", "fits"):
        with pytest.raises(UserError):
            parse_settings({key: {}})


def test_annotation_ids_are_made_unique():
    s = parse_settings({"annotations": [{"id": "a1", "y": 1}, {"id": "a1", "y": 2}, {"y": 3}]})
    assert len({a.id for a in s.annotations}) == 3


# ---------------------------------------------------------------- Phase 5c: グラフの種類（G7）の項目


def test_5c_plot_defaults():
    d = default_settings()
    assert d["plot"]["step"] == {"where": "post"}
    assert d["plot"]["hist"] == {"bins": None, "density": False}
    assert (d["plot"]["colormap"], d["plot"]["colorbarLabel"]) == ("viridis", "")
    assert d["series"][0]["colorColumn"] == ""


def test_5c_new_types_and_hidden_settings():
    for t in ("step", "barh", "barStacked", "hist"):
        raw = default_settings()
        raw["plot"]["type"] = t
        assert parse_settings(raw).plot.type == t
    raw = default_settings()
    raw["plot"]["type"] = "line"
    raw["plot"].update(step={"where": "x"}, hist={"bins": -1}, colormap="zzz")  # 隠れているので検証しない
    s = parse_settings(raw).plot
    assert (s.step_where, s.hist_bins, s.colormap) == ("post", None, "viridis")
    raw["plot"]["type"] = "scatterColor"
    with pytest.raises(UserError) as e:
        parse_settings(raw)
    assert e.value.field == "カラーマップ"
