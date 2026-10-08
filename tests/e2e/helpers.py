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


# --- Pythonコードタブ ---
# <html data-code-mode="sync|edit">、#customPyCode（data-generation）、#codeOutput（data-kind）、#codeSyncStatus、
# `#plotArea img` の data-summary（図の要約 JSON）。
def code_mode(page) -> str:
    return page.evaluate("document.documentElement.dataset.codeMode || ''")


def code_text(page) -> str:
    return page.input_value("#customPyCode")


def code_generation(page) -> str:
    return page.evaluate("document.getElementById('customPyCode').dataset.generation || ''")


def open_code_tab(page):
    page.click("#tabCodeBtn")


def wait_code_generated(page, timeout=120_000):
    """GUI 同期のコードが、表示中の画像と同じ世代で textarea に入るまで待つ。"""
    page.wait_for_function(
        """() => {
          const img = document.querySelector('#plotArea img');
          const code = document.getElementById('customPyCode');
          return !!img && !!code.value && code.dataset.generation === img.dataset.generation;
        }""",
        timeout=timeout,
    )


def enter_edit_mode(page):
    open_code_tab(page)
    page.click("#editCodeBtn")
    page.wait_for_function("document.documentElement.dataset.codeMode === 'edit'")


def wait_image_generation_changed(page, previous, timeout=120_000):
    """表示中の画像の世代が previous から変わり、描画要求が残っていないところまで待つ。新しい世代を返す。"""
    page.wait_for_function(
        """(prev) => {
          const d = document.documentElement.dataset;
          const img = document.querySelector('#plotArea img');
          return d.renderState === 'idle' && !!img && img.dataset.generation !== prev
            && img.dataset.generation === d.renderGeneration;
        }""",
        arg=previous,
        timeout=timeout,
    )
    return image_generation(page)


def run_edited_code(page, how="button"):
    """編集モードのコードを実行し、描画が一段落するまで待つ（画像の世代が進む）。"""
    previous = image_generation(page)
    if how == "button":
        page.click("#applyCustomCodeBtn")
    else:
        page.focus("#customPyCode")
        page.keyboard.press("ControlOrMeta+Enter")
    return wait_image_generation_changed(page, previous)


def wait_run_finished(page, timeout=120_000):
    """実行（成功・失敗とも）が終わるまで待つ。"""
    page.wait_for_function("document.documentElement.dataset.renderState === 'idle'", timeout=timeout)


def image_summary(page):
    import json

    raw = page.evaluate("(document.querySelector('#plotArea img') || {dataset: {}}).dataset.summary || ''")
    return json.loads(raw) if raw else None


def code_output(page) -> str:
    return page.inner_text("#codeOutput")


def code_output_kind(page) -> str:
    return page.get_attribute("#codeOutput", "data-kind") or ""


# --- 体裁セクション（プリセット・パレット・図サイズの単位） ---
def natural_size(page) -> tuple[int, int]:
    """表示中のプレビュー画像の実寸（ピクセル）。"""
    w, h = page.evaluate("(() => { const i = document.querySelector('#plotArea img'); return [i.naturalWidth, i.naturalHeight]; })()")
    return w, h


def act_and_wait_render(page, action):
    """action() を実行し、設定変更による再描画が終わる（画像の世代が進む）まで待つ。"""
    previous = image_generation(page)
    action()
    wait_image_generation_changed(page, previous)


def series_color(page, series_id) -> str:
    return page.evaluate("(id) => document.querySelector(`#series-${id}-color-trigger`).closest('.series-item').querySelector('.series-color-value').textContent", series_id)


def palette_grid_colors(page, series_id) -> list[str]:
    """系列の色選択パネルに並ぶ色（パネルを開かなくても DOM にある）。"""
    return page.evaluate(
        "(id) => [...document.querySelector(`#series-${id}-color-trigger`).closest('.series-item').querySelectorAll('.series-color-chip')].map(c => c.dataset.color.toUpperCase())",
        series_id,
    )


# --- 保存セクション・欧文フォント・クリップボード ---
# <html data-latin-font-state="idle|loading|ready|failed">（選択中の欧文フォント）、data-copy-state="idle|copying|done|failed|unsupported"
ARIMO_GLOB = "**/Arimo_400Regular.ttf"
TINOS_GLOB = "**/Tinos_400Regular.ttf"


def image_size(data: bytes) -> tuple[int, int]:
    """PNG / JPG のバイト列から画像の大きさ（幅, 高さ）を読む。"""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return image.size


def save_bytes(page, timeout=120_000) -> bytes:
    """保存ボタンを押し、ダウンロードされたファイルの中身を返す。"""
    return open(save_plot(page, timeout).path(), "rb").read()


def set_save_dpi(page, dpi):
    """プリセット（72 / 150 / 300 / 600）か、それ以外なら「任意」を選んで値を入れる。"""
    if str(dpi) in {"72", "150", "300", "600"}:
        page.select_option("#saveDpi", str(dpi))
    else:
        page.select_option("#saveDpi", "custom")
        page.fill("#saveDpiCustom", str(dpi))


def latin_font_state(page) -> str:
    return page.evaluate("document.documentElement.dataset.latinFontState || ''")


def wait_latin_state(page, state, timeout=120_000):
    page.wait_for_function(
        "(s) => document.documentElement.dataset.latinFontState === s", arg=state, timeout=timeout
    )


def copy_state(page) -> str:
    return page.evaluate("document.documentElement.dataset.copyState || ''")


def wait_copy_state(page, state, timeout=120_000):
    page.wait_for_function("(s) => document.documentElement.dataset.copyState === s", arg=state, timeout=timeout)


def read_clipboard_png_size(page) -> tuple[int, int]:
    """クリップボードの画像（image/png）の大きさ。"""
    return tuple(
        page.evaluate(
            """async () => {
              const items = await navigator.clipboard.read();
              const blob = await items[0].getType('image/png');
              const bitmap = await createImageBitmap(blob);
              return [bitmap.width, bitmap.height];
            }"""
        )
    )


def wait_code_contains(page, text, timeout=60_000):
    page.wait_for_function(
        "(t) => document.getElementById('customPyCode').value.includes(t)", arg=text, timeout=timeout
    )


# --- データ読み込みの設定（シート・ヘッダより前の行・桁区切り・小数点・コメント記号） ---
def change_load_option(page, action):
    """action() で読込設定を変え、読み直し（data-load-count が増える）と再描画が済むまで待つ。"""
    before = load_count(page)
    action()
    wait_load_count(page, before + 1)
    wait_settled(page)


def set_load_options(page, *, delimiter=None, skip_lines=None, thousands=None, decimal=None, comment=None):
    """ファイルを選ぶ前に、読込設定を入れておく（ファイルが無いので読み直しは起こらない）。"""
    if delimiter is not None:
        page.fill("#delimiter", delimiter)
    if skip_lines is not None:
        page.fill("#skipLines", str(skip_lines))
    if thousands is not None:
        page.select_option("#thousands", thousands)
    if decimal is not None:
        page.select_option("#decimal", decimal)
    if comment is not None:
        page.fill("#commentChar", comment)


def sheet_options(page) -> list[str]:
    return page.evaluate("[...document.querySelectorAll('#sheetSelect option')].map(o => o.value)")


def code_is_stale(page) -> bool:
    """コードタブの「最新でない」表示（#customPyCode の data-stale と #codeStaleNote）。"""
    attr = page.evaluate("document.getElementById('customPyCode').dataset.stale || ''") == "true"
    note = page.evaluate("!document.getElementById('codeStaleNote').hidden")
    assert attr == note, "data-stale と #codeStaleNote の表示が食い違っている"
    return attr
