"""PyScript のエントリ。JS と mplgui の橋渡しだけを行う（DOM には触れない）。

JS（js/bridge.js）は window.mplgui の関数を呼ぶ。引数・戻り値は JSON 文字列。
"""
import warnings

import matplotlib

matplotlib.use("Agg")  # ブラウザ描画バックエンドを使わない（pyplot を import する前に指定する）

warnings.simplefilter("ignore", DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Pyarrow will become a required dependency of pandas.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*missing from current font.*", category=UserWarning)

from js import CustomEvent, Object, window  # noqa: E402
from pyodide.ffi import create_proxy  # noqa: E402

from mplgui import api  # noqa: E402
from mplgui.fonts import configure_rcparams  # noqa: E402

configure_rcparams()


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


# create_proxy の参照を保持しておく（GC されると JS から呼べなくなる）
_PROXIES = {
    "loadFile": create_proxy(_load_file),
    "render": create_proxy(_render),
    "save": create_proxy(_save),
    "registerFont": create_proxy(_register_font),
    "fontStatus": create_proxy(api.font_status),
    "defaultCustomCode": create_proxy(api.default_custom_code),
}
_API = Object.new()
for _name, _proxy in _PROXIES.items():
    setattr(_API, _name, _proxy)

window.mplgui = _API
window.dispatchEvent(CustomEvent.new("mplgui-ready"))
