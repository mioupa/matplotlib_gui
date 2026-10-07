"""JS から呼ばれる JSON 入出力の API（純粋な Python。js / pyodide には依存しない）。

py/main.py はこの関数を window.mplgui に登録するだけ。引数・戻り値はすべて JSON 文字列（ファイル/フォントはバイト列）。
成功: {"ok": true, ...}  失敗: {"ok": false, "error": {"message", "field"?, "detail"?}}
"""
from __future__ import annotations

import json
import traceback

import matplotlib.pyplot as plt

from . import fonts
from .errors import UserError
from .loader import PREVIEW_ROWS, build_preview, column_options, load_file
from .runner import (
    DEFAULT_CUSTOM_PLOT_CODE,
    build_filename,
    figure_to_data_uri,
    make_figure,
)
from .settings import parse_load_settings, parse_settings

INTERNAL_ERROR_MESSAGE = "内部エラーが発生しました。もう一度操作してください。"


class Session:
    """読み込み済みデータ（ブラウザのタブごとに1つ）。"""

    def __init__(self):
        self.df = None
        self.filename = None


SESSION = Session()


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _error_payload(exc: BaseException, context: str) -> dict:
    if isinstance(exc, UserError):
        return {"ok": False, "error": exc.to_dict()}
    detail = f"context: {context}\ntype: {type(exc).__name__}\nmessage: {exc}\n\ntraceback:\n{traceback.format_exc().strip()}"
    return {"ok": False, "error": {"message": INTERNAL_ERROR_MESSAGE, "detail": detail}}


def _guard(context: str):
    def deco(fn):
        def wrapper(*args, **kwargs):
            try:
                return _dumps(fn(*args, **kwargs))
            except Exception as exc:  # noqa: BLE001 - 境界。UserError 以外は内部エラーとして詳細つきで返す
                return _dumps(_error_payload(exc, context))

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return deco


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise UserError("設定を解釈できませんでした。ページを再読み込みしてください。", detail=str(exc)) from exc
    return data


@_guard("load_file")
def load_file_json(name: str, data: bytes, load_settings_json: str) -> dict:
    """ファイルを読み込み、列の選択肢とプレビューを返す。失敗時は読込済みデータを破棄する。"""
    SESSION.df = None
    SESSION.filename = None
    load = parse_load_settings(_parse_json(load_settings_json))
    loaded = load_file(bytes(data), name, load.delimiter, load.has_header)
    SESSION.df = loaded.df
    SESSION.filename = name
    return {
        "ok": True,
        "encoding": loaded.encoding,
        "columns": column_options(loaded.df),
        "preview": build_preview(loaded.df, PREVIEW_ROWS),
        "warnings": [],
    }


def _figure_for(settings_json: str, custom_code: str | None):
    settings = parse_settings(_parse_json(settings_json))
    if SESSION.df is None:
        raise UserError("先にファイルを読み込んでください。")
    return settings, make_figure(SESSION.df, settings, custom_code)


@_guard("render")
def render_json(settings_json: str, custom_code: str | None = None) -> dict:
    """設定どおりに描画し、PNG の data URI を返す。"""
    _, result = _figure_for(settings_json, custom_code)
    try:
        uri, _ext = figure_to_data_uri(result.fig, "png", dpi=100)
    finally:
        plt.close(result.fig)
    return {
        "ok": True,
        "image": uri,
        "seriesCount": result.plotted_count,
        "skipRows": result.skip_rows,
        "warnings": result.warnings,
    }


@_guard("save")
def save_json(settings_json: str, custom_code: str | None = None) -> dict:
    """保存設定の形式で図を書き出し、data URI とファイル名を返す（ダウンロードは JS が行う）。"""
    settings, result = _figure_for(settings_json, custom_code)
    try:
        uri, ext = figure_to_data_uri(result.fig, settings.save.format, transparent=settings.save.transparent)
    finally:
        plt.close(result.fig)
    mime = uri[5 : uri.index(";")]
    return {"ok": True, "filename": build_filename(settings.save.filename, ext), "mime": mime, "dataUri": uri}


def register_font(data: bytes) -> str:
    """JS が取得した日本語フォントを登録する。"""
    try:
        return _dumps({"ok": True, "registered": fonts.register_font_bytes(bytes(data))})
    except Exception as exc:  # noqa: BLE001
        return _dumps(_error_payload(exc, "register_font"))


def font_status() -> str:
    return _dumps({"ok": True, "registered": fonts.is_registered()})


def default_custom_code() -> str:
    return DEFAULT_CUSTOM_PLOT_CODE.strip() + "\n"
