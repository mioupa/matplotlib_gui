"""PyScript のエントリ。JS と mplgui の橋渡しだけを行う（DOM には触れない）。

JS（js/bridge.js）は window.mplgui の関数を呼ぶ。引数・戻り値は JSON 文字列。
"""
import asyncio
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # ブラウザ描画バックエンドを使わない（pyplot を import する前に指定する）

from mplgui.runtime import configure_warnings  # noqa: E402

configure_warnings()

from js import CustomEvent, Object, window  # noqa: E402
from pyodide.ffi import create_proxy, to_js  # noqa: E402

from mplgui import api  # noqa: E402
from mplgui.errors import UserError  # noqa: E402
from mplgui.fonts import configure_rcparams  # noqa: E402

configure_rcparams()

# ブラウザ内で実行するスクリプトが、アップロードしたファイルを元のファイル名で読めるように、作業フォルダに置く
api.SESSION.workdir = Path.cwd()


# openpyxl / et_xmlfile は Pyodide 同梱ではない。バージョン固定の wheel URL を Pyodide の loadPackage に直接渡す
# （micropip と PyPI の問い合わせを避ける）。URL は PyPI JSON API で確認した files.pythonhosted.org の正規 URL。
_EXCEL_WHEELS = [
    "https://files.pythonhosted.org/packages/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/et_xmlfile-2.0.0-py3-none-any.whl",
    "https://files.pythonhosted.org/packages/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/openpyxl-3.1.5-py2.py3-none-any.whl",
]
_EXCEL_STATE = {"ready": False, "task": None}


def _excel_available():
    import importlib.util

    return importlib.util.find_spec("openpyxl") is not None


async def _install_excel():
    import pyodide_js

    await pyodide_js.loadPackage(to_js(_EXCEL_WHEELS))


async def _ensure_excel():
    """初回の .xlsx 読込前に JS から呼ぶ。2回目以降は何もしない。戻り値は JSON 文字列。"""
    if _EXCEL_STATE["ready"] or _excel_available():
        _EXCEL_STATE["ready"] = True
        return json.dumps({"ok": True})
    try:
        if _EXCEL_STATE["task"] is None:
            _EXCEL_STATE["task"] = asyncio.ensure_future(_install_excel())
        await _EXCEL_STATE["task"]
        if not _excel_available():
            raise RuntimeError("openpyxl を導入後も import できません")
        _EXCEL_STATE["ready"] = True
        return json.dumps({"ok": True})
    except Exception as exc:
        _EXCEL_STATE["task"] = None  # 次回は再試行する
        err = UserError(
            "Excel読込用のライブラリを取得できませんでした。ネットワーク接続を確認して、もう一度ファイルを選択するか、"
            "CSVで保存し直してから読み込んでください。",
            field="入力ファイル",
            detail=f"{type(exc).__name__}: {exc}",
        )
        return json.dumps({"ok": False, "error": err.to_dict()}, ensure_ascii=False)


def _load_file(name, data, load_settings_json):
    return api.load_file_json(str(name), data.to_py(), str(load_settings_json))


def _code(value):
    # JS の null / undefined は Python では None とは限らない（jsnull）。文字列のときだけコードとして扱う
    return value if isinstance(value, str) else None


def _render(settings_json, custom_code=None):
    return api.render_json(str(settings_json), _code(custom_code))


def _save(settings_json, custom_code=None):
    return api.save_json(str(settings_json), _code(custom_code))


def _register_font(data):
    return api.register_font(data.to_py())


def _script_filename(save_filename):
    return api.script_filename(save_filename if isinstance(save_filename, str) else "")


# create_proxy の参照を保持しておく（GC されると JS から呼べなくなる）
_PROXIES = {
    "ensureExcel": create_proxy(_ensure_excel),
    "loadFile": create_proxy(_load_file),
    "render": create_proxy(_render),
    "save": create_proxy(_save),
    "scriptFilename": create_proxy(_script_filename),
    "registerFont": create_proxy(_register_font),
    "fontStatus": create_proxy(api.font_status),
}
_API = Object.new()
for _name, _proxy in _PROXIES.items():
    setattr(_API, _name, _proxy)

window.mplgui = _API
window.dispatchEvent(CustomEvent.new("mplgui-ready"))
