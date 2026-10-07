"""静的HTTPサーバー（stdlib）。E2Eとベンチマークで共用する。

base_path（例: "/matplotlib_gui/"）を指定すると、GitHub Pages のプロジェクトサイトと同様に
そのサブパス配下でのみ配信する（範囲外のリクエストは404）。絶対パス参照の検出に使う。
"""
import functools
import http.server
import os
import threading
from pathlib import Path


def normalize_base_path(base_path: str | None) -> str:
    bp = (base_path or "/").strip()
    return "/" + bp.strip("/") + "/" if bp.strip("/") else "/"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    base_path = "/"

    def log_message(self, *a, **k):
        pass

    def translate_path(self, path):
        bp = self.base_path
        if bp != "/":
            raw = path.split("?", 1)[0].split("#", 1)[0]
            if raw == bp.rstrip("/"):
                return os.devnull + "/__outside__"  # send_head が 404 にする
            if not raw.startswith(bp):
                return os.devnull + "/__outside__"
            path = "/" + path[len(bp):]
        return super().translate_path(path)


def start_server(directory, base_path: str | None = None) -> tuple[http.server.ThreadingHTTPServer, str]:
    bp = normalize_base_path(base_path)
    handler_cls = type("_Handler", (_Quiet,), {"base_path": bp})
    handler = functools.partial(handler_cls, directory=str(Path(directory)))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}{bp}"
