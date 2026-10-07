import json
from pathlib import Path

import pytest

from mplgui import api
from mplgui.settings import default_settings

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(autouse=True)
def fresh_session():
    api.SESSION.df = None
    yield
    api.SESSION.df = None


def load(name="utf8.csv", settings=None):
    s = settings or default_settings()
    return json.loads(api.load_file_json(name, (FIXTURES / name).read_bytes(), json.dumps(s)))


def test_load_file_response_shape():
    r = load()
    assert r["ok"] is True and r["encoding"] == "utf-8" and r["warnings"] == []
    assert r["columns"][0] == {"value": "__idx__0", "label": "時間 [0]"}
    assert r["preview"]["totalRows"] == 30


def test_render_before_load_is_user_error():
    r = json.loads(api.render_json(json.dumps(default_settings())))
    assert r["ok"] is False and "ファイルを読み込んで" in r["error"]["message"]


def test_render_response_shape():
    load()
    r = json.loads(api.render_json(json.dumps(default_settings())))
    assert r["ok"] is True and r["image"].startswith("data:image/png;base64,")
    assert r["seriesCount"] == 1 and r["skipRows"] == 0 and r["warnings"] == []


def test_render_validation_error_is_field_specific():
    load()
    s = default_settings()
    s["plot"]["fontSize"] = "x"
    r = json.loads(api.render_json(json.dumps(s)))
    assert r["ok"] is False and "フォントサイズ" in r["error"]["message"] and r["error"]["field"] == "フォントサイズ"
    assert "detail" not in r["error"]


def test_bad_json_is_user_error():
    r = json.loads(api.render_json("{not json"))
    assert r["ok"] is False and not r["error"]["message"].isascii()


def test_internal_error_has_short_message_and_traceback(monkeypatch):
    load()

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api, "make_figure", boom)
    r = json.loads(api.render_json(json.dumps(default_settings())))
    assert r["ok"] is False and r["error"]["message"] == api.INTERNAL_ERROR_MESSAGE
    assert "RuntimeError" in r["error"]["detail"] and "kaboom" in r["error"]["detail"] and "Traceback" in r["error"]["detail"]


def test_load_failure_discards_previous_data():
    load()
    bad = json.loads(api.load_file_json("x.pdf", b"x", json.dumps(default_settings())))
    assert bad["ok"] is False and api.SESSION.df is None


def test_save_response():
    load()
    s = default_settings()
    s["save"].update(filename="結果.csv", format="svg")
    r = json.loads(api.save_json(json.dumps(s)))
    assert r["ok"] and r["filename"] == "結果.svg" and r["mime"] == "image/svg+xml"
    assert r["dataUri"].startswith("data:image/svg+xml;base64,")
    s["save"].update(format="jpg", transparent=True)
    r = json.loads(api.save_json(json.dumps(s)))
    assert r["ok"] is False and "背景透過" in r["error"]["message"]


def test_render_with_custom_code():
    load()
    r = json.loads(api.render_json(json.dumps(default_settings()), api.default_custom_code()))
    assert r["ok"] is True
    r = json.loads(api.render_json(json.dumps(default_settings()), "raise ValueError('x')"))
    assert r["ok"] is False and "カスタムコード" in r["error"]["message"]


def test_font_status_before_register():
    assert json.loads(api.font_status())["ok"] is True


# ---------------------------------------------------------------- B7: Japanese errors everywhere

FORBIDDEN = ("invalid literal", "could not convert", "Traceback", "Error:", "Exception", "object has no attribute")


def _s(mutator):
    s = default_settings()
    mutator(s)
    return s


def _set(path, value):
    def mut(s):
        node = s
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mut


BAD_SETTINGS = [
    ("fontSize abc", _set(["plot", "fontSize"], "abc")),
    ("fontSize 0", _set(["plot", "fontSize"], 0)),
    ("fontSize list", _set(["plot", "fontSize"], [1])),
    ("skipRows 1.5", _set(["plot", "skipRows"], 1.5)),
    ("skipRows x", _set(["plot", "skipRows"], "x")),
    ("skipRows -1", _set(["plot", "skipRows"], -1)),
    ("skipRows too big", _set(["plot", "skipRows"], 1000)),
    ("figure width x", _set(["plot", "figure", "width"], "x")),
    ("figure width huge", _set(["plot", "figure", "width"], 1e9)),
    ("figure height 0", _set(["plot", "figure", "height"], 0)),
    ("type pie", _set(["plot", "type"], "pie")),
    ("title number", _set(["plot", "title"], 123)),
    ("legend bad", _set(["plot", "legend", "location"], "nowhere")),
    ("grid bad", _set(["plot", "grid", "major"], "yes")),
    ("margin 2", _set(["plot", "margins", "left"], 2)),
    ("margin x", _set(["plot", "margins", "top"], "x")),
    ("margin order", lambda s: s["plot"]["margins"].update(left=0.9, right=0.1)),
    ("x min x", _set(["axes", "x", "min"], "abc")),
    ("x min >= max", lambda s: s["axes"]["x"].update(min=5, max=1)),
    ("y log negative", lambda s: s["axes"]["y"].update(scale="log", min=-1, max=10)),
    ("scale bad", _set(["axes", "y", "scale"], "sqrt")),
    ("no series", _set(["series"], [])),
    ("series color bad", _set(["series", 0, "color"], "notacolor")),
    ("series lineWidth x", _set(["series", 0, "lineWidth"], "x")),
    ("series lineWidth 0", _set(["series", 0, "lineWidth"], 0)),
    ("series marker x", _set(["series", 0, "markerSize"], "x")),
    ("series style bad", _set(["series", 0, "lineStyle"], "wavy")),
    ("series col out of range", _set(["series", 0, "y"], "__idx__99")),
    ("series col not found", _set(["series", 0, "y"], "nonexistent")),
    ("series col malformed", _set(["series", 0, "y"], "__idx__x")),
    ("series x out of range", _set(["series", 0, "x"], "__idx__50")),
    ("version", _set(["version"], 99)),
    ("save format gif", _set(["save", "format"], "gif")),
]
SAVE_ONLY = [("save transparent jpg", lambda s: s["save"].update(format="jpg", transparent=True))]


def _assert_japanese_clean(r):
    assert r["ok"] is False
    msg = r["error"]["message"]
    assert not msg.isascii(), msg
    for bad in FORBIDDEN:
        assert bad not in msg, (bad, msg)


@pytest.mark.parametrize(
    "name, mutator, entry",
    [(n, m, e) for n, m in BAD_SETTINGS for e in (api.render_json, api.save_json)] + [(n, m, api.save_json) for n, m in SAVE_ONLY],
    ids=lambda v: v if isinstance(v, str) else getattr(v, "__name__", "f"),
)
def test_bad_settings_give_clean_japanese_errors(name, mutator, entry):
    load()
    r = json.loads(entry(json.dumps(_s(mutator))))
    _assert_japanese_clean(r)
    assert r["error"]["message"] != api.INTERNAL_ERROR_MESSAGE  # 想定内のユーザー入力ミスは内部エラー扱いにしない


BAD_FILES = [
    ("unsupported ext", "a.pdf", b"x", ""),
    ("empty", "e.csv", b"", ""),
    ("header only", "h.csv", b"a,b\n", ""),
    ("undecodable", "u.csv", b"a,b\n\xff\xff\xff\xff\n", ""),
    ("ragged", "r.csv", b"a,b\n1,2\n1,2,3,4,5\n6,7\n", ","),
    ("bad regex", "x.txt", b"a b\n1 2\n", "(a"),
    ("bad escape", "x.csv", b"a,b\n1,2\n", "\\x"),
    ("broken xlsx", "b.xlsx", b"not a zip", ""),
]


@pytest.mark.parametrize("name, fname, data, delim", BAD_FILES, ids=[b[0] for b in BAD_FILES])
def test_bad_files_give_clean_japanese_errors(name, fname, data, delim):
    s = default_settings()
    s["load"]["delimiter"] = delim
    r = json.loads(api.load_file_json(fname, data, json.dumps(s)))
    _assert_japanese_clean(r)
    assert r["error"]["message"] != api.INTERNAL_ERROR_MESSAGE


def test_render_without_data_and_bad_json_are_clean():
    _assert_japanese_clean(json.loads(api.render_json(json.dumps(default_settings()))))
    _assert_japanese_clean(json.loads(api.render_json("{broken")))
    _assert_japanese_clean(json.loads(api.load_file_json("a.csv", b"a\n1\n", "{broken")))


def test_unparsable_values_only_series_error_is_japanese():
    load("non_numeric.csv")
    s = _s(_set(["series", 0, "y"], "__idx__3"))
    _assert_japanese_clean(json.loads(api.render_json(json.dumps(s))))


def test_unexpected_mismatch_error_is_wrapped_with_detail(monkeypatch):
    import matplotlib.axes

    load()

    def boom(self, *a, **k):
        raise TypeError("cannot cast array data")

    monkeypatch.setattr(matplotlib.axes.Axes, "plot", boom)
    r = json.loads(api.render_json(json.dumps(default_settings())))
    _assert_japanese_clean(r)
    assert "cannot cast" in r["error"]["detail"]
