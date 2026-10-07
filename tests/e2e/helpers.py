"""アプリ固有の待機・操作ロジックはすべてここに置く（要素は id のみで選ぶ）。

使用する信号（現行 index.html）:
- アプリ準備完了: PyScript の初期化末尾で Python が `window.requestRender` /
  `window.requestLoadColumns` を登録する。`typeof window.requestRender === 'function'`
  を「Python準備完了」とする。
- データ読込完了: `window.__matplotDataReady === true`（読込開始時に false、完了時に true）。
- プロット更新: `#plotArea img` の src（PNG data URI）が変化したこと。
  描画のたびに innerHTML ごと置き換えられる。
"""
import time

READY_JS = "typeof window.requestRender === 'function' && typeof window.requestLoadColumns === 'function'"
DATA_READY_JS = "window.__matplotDataReady === true"
PLOT_SRC_JS = "(document.querySelector('#plotArea img') || {}).src || ''"


class ConsoleCollector:
    def __init__(self, page):
        self.events = []  # (経過秒, 種別, 文言)
        self.t0 = time.time()
        self.stage = "startup"
        page.on("console", self._on_console)
        page.on("pageerror", lambda e: self._add("pageerror", str(e)))

    def _on_console(self, msg):
        if msg.type == "error":
            self._add("console.error", msg.text)

    def _add(self, kind, text):
        self.events.append((round(time.time() - self.t0, 1), self.stage, kind, text[:500]))

    def mark(self, stage):
        self.stage = stage

    def parentnode(self):
        return [e for e in self.events if "parentNode" in e[3]]

    def report(self):
        print(f"\n[console-errors] total={len(self.events)} parentNode={len(self.parentnode())}")
        for t, stage, kind, text in self.events:
            print(f"  [{t}s][{stage}][{kind}] {text}")


def wait_app_ready(page, timeout=300_000):
    page.wait_for_function(READY_JS, timeout=timeout)


def wait_data_ready(page, timeout=120_000):
    page.wait_for_function(DATA_READY_JS, timeout=timeout)


def plot_src(page) -> str:
    return page.evaluate(PLOT_SRC_JS)


def load_fixture(page, path):
    """ファイル入力に設定する。自動読込→データ準備完了まで待つ。"""
    page.set_input_files("#fileInput", str(path))
    wait_data_ready(page)


def wait_plot_changed(page, previous_src, timeout=120_000):
    """プロット画像のsrcが previous_src から変わる（新規表示を含む）まで待つ。新しいsrcを返す。"""
    page.wait_for_function(
        f"(prev) => {{ const s = {PLOT_SRC_JS}; return s !== '' && s !== prev; }}",
        arg=previous_src,
        timeout=timeout,
    )
    return plot_src(page)


def set_title(page, text):
    page.fill("#title", text)  # input イベントで250msデバウンス後に再描画


def save_plot(page, timeout=120_000):
    """保存ボタンを押してダウンロードを返す。"""
    with page.expect_download(timeout=timeout) as dl:
        page.click("#savePlotBtn")
    return dl.value
