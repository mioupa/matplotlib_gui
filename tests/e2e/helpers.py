"""アプリ固有の待機・操作ロジックはすべてここに置く（要素は id のみで選ぶ）。

使用する信号（<html> の data 属性。js/bridge.js が更新する）:
- data-app-state: "starting" → "ready"（Python 起動完了）
- data-data-state: "none" | "loading" | "ready" | "error"（データ読込）
- data-render-state: "idle" | "pending"（デバウンス待ち）| "rendering"
- data-render-generation: 最新の描画要求の世代番号。表示中の `#plotArea img` は data-generation を持つ。
- `#status` の data-kind: "" | "ok" | "error"
"""
import time

READY_JS = "document.documentElement.dataset.appState === 'ready'"
DATA_READY_JS = "document.documentElement.dataset.dataState === 'ready'"
PLOT_SRC_JS = "(document.querySelector('#plotArea img') || {}).src || ''"
# 描画要求が残っておらず、表示中の画像が最新の要求のものになっている
SETTLED_JS = """() => {
  const d = document.documentElement.dataset;
  const img = document.querySelector('#plotArea img');
  return d.renderState === 'idle' && d.dataState !== 'loading'
    && (!d.renderGeneration || (img && img.dataset.generation === d.renderGeneration)
        || document.getElementById('status').dataset.kind === 'error');
}"""


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

    def report(self):
        print(f"\n[console-errors] total={len(self.events)}")
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


def wait_settled(page, timeout=120_000):
    """読込・描画が一段落するまで待つ（エラー終了を含む）。"""
    page.wait_for_function(SETTLED_JS, timeout=timeout)


def status_text(page) -> str:
    return page.inner_text("#status")


def status_kind(page) -> str:
    return page.get_attribute("#status", "data-kind") or ""


def set_title(page, text):
    page.fill("#title", text)  # input イベントで250msデバウンス後に再描画


def save_plot(page, timeout=120_000):
    """保存ボタンを押してダウンロードを返す。"""
    with page.expect_download(timeout=timeout) as dl:
        page.click("#savePlotBtn")
    return dl.value


# --- Step 5a で追加した信号 ---
# data-font-state: "idle" | "loading" | "ready" | "failed"（日本語フォント）
# data-load-count: 読込が成功した回数
FONT_DONE_JS = "['ready','failed'].includes(document.documentElement.dataset.fontState)"
STATUS_WARNINGS_JS = "[...document.querySelectorAll('#status .status-warning-item')].map(e => e.textContent)"


def wait_font_done(page, timeout=180_000):
    page.wait_for_function(FONT_DONE_JS, timeout=timeout)


def load_count(page) -> int:
    return int(page.evaluate("document.documentElement.dataset.loadCount || '0'"))


def wait_load_count(page, n, timeout=120_000):
    page.wait_for_function(f"Number(document.documentElement.dataset.loadCount) >= {int(n)}", timeout=timeout)


def render_generation(page) -> str:
    return page.evaluate("document.documentElement.dataset.renderGeneration || ''")


def image_generation(page) -> str:
    return page.evaluate("(document.querySelector('#plotArea img') || {dataset: {}}).dataset.generation || ''")


def status_warnings(page) -> list[str]:
    return page.evaluate(STATUS_WARNINGS_JS)
