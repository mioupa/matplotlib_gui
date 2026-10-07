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
