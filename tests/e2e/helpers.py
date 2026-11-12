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


# --- ドロップ・貼り付け（D1） ---
DRAG_JS = """([type, selector, files, text]) => {
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(new File([new Uint8Array(f.bytes)], f.name));
  if (text !== null) dt.setData('text/plain', text);
  const target = document.querySelector(selector);
  const event = new DragEvent(type, {dataTransfer: dt, bubbles: true, cancelable: true});
  target.dispatchEvent(event);
  return event.defaultPrevented;
}"""


def drag_event(page, type_, selector="body", files=(), text=None) -> bool:
    """ファイル（名前, バイト列）や文字列を持つ DragEvent を要素に送る。defaultPrevented を返す。"""
    payload = [{"name": name, "bytes": list(data)} for name, data in files]
    return page.evaluate(DRAG_JS, [type_, selector, payload, text])


def drop_files(page, files, selector="body"):
    """ドロップの一連のイベント（dragenter → dragover → drop）を送る。"""
    drag_event(page, "dragenter", selector, files)
    drag_event(page, "dragover", selector, files)
    return drag_event(page, "drop", selector, files)


def drop_overlay_visible(page) -> bool:
    return page.evaluate("!document.getElementById('dropOverlay').hidden")


PASTE_JS = """([selector, text]) => {
  const target = selector ? document.querySelector(selector) : document.body;
  if (selector) target.focus();
  const dt = new DataTransfer();
  dt.setData('text/plain', text);
  const event = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
  target.dispatchEvent(event);
  return event.defaultPrevented;
}"""


def paste_text(page, text, selector="#pasteArea") -> bool:
    """ClipboardEvent('paste') を送る（selector=None は body）。defaultPrevented を返す。"""
    return page.evaluate(PASTE_JS, [selector, text])


EXCEL_TABLE = "時間\t電圧\t電流\r\n0\t0\t1.5\r\n1\t0.5\t1.4\r\n2\t0.9\t1.1\r\n3\t1.0\t0.8\r\n"


# --- 複数ファイル（D6） ---
def add_files(page, paths, selector="#addFileInput", timeout=120_000):
    """ファイルを追加（または selector で置き換え）し、読み込みと描画が済むまで待つ。"""
    before = load_count(page)
    page.set_input_files(selector, [str(p) for p in paths])
    wait_load_count(page, before + 1, timeout=timeout)
    wait_settled(page, timeout=timeout)


def file_row_ids(page) -> list[str]:
    """一覧（#fileList）の行の id（file-d1 など）。"""
    return page.evaluate("[...document.querySelectorAll('#fileList .file-row')].map(e => e.id)")


def file_row_states(page) -> dict[str, str]:
    return page.evaluate("Object.fromEntries([...document.querySelectorAll('#fileList .file-row')].map(e => [e.id, e.dataset.state]))")


def settings_files(page) -> list[dict]:
    """画面のファイル一覧に対応する、データ元セレクト（#previewSource）の選択肢の値。"""
    return page.evaluate("[...document.querySelectorAll('#previewSource option')].map(o => o.value)")


def add_series_with_source(page, source, y="__idx__1", series_id="s2"):
    """系列を追加し、データ元と Y 列を選ぶ。"""
    page.click("#addSeriesBtn")
    page.select_option(f"#series-{series_id}-source", source)
    page.select_option(f"#series-{series_id}-y", y)
    wait_settled(page)


def remove_file(page, file_id):
    """ファイルを取り除く。一覧の削除ボタンは2ファイル以上のときだけ出るので、最後の1つは bridge.js の removeFile で取り除く。"""
    if page.locator(f"#file-{file_id}-remove").count() > 0:
        page.click(f"#file-{file_id}-remove")
    else:
        page.evaluate("(id) => import(new URL('js/bridge.js', document.baseURI)).then((m) => m.removeFile(id))", file_id)


# --- 目盛・枠線・日時の範囲（Phase 5a） ---
def open_tick_group(page, axis):
    """軸の目盛の折りたたみ（#xTickGroup / #yTickGroup / #y2TickGroup）を開く（開く操作は設定を変えない）。"""
    page.evaluate("(id) => { document.getElementById(id).open = true; }", f"{axis}TickGroup")


def set_axis_option(page, selector, value, *, wait=True):
    """目盛などの入力欄を変える。wait=True なら、再描画（画像の世代が進む）まで待つ。値の種類は要素から決める。"""

    def act():
        kind = page.evaluate(
            "(s) => { const e = document.querySelector(s); return e.type === 'checkbox' ? 'checkbox' : e.tagName.toLowerCase(); }",
            selector,
        )
        if kind == "checkbox":
            page.set_checked(selector, bool(value))
        elif kind == "select":
            page.select_option(selector, value)
        else:
            page.fill(selector, str(value))

    if wait:
        act_and_wait_render(page, act)
    else:
        act()


def wait_error_status(page, timeout=60_000):
    page.wait_for_function("document.getElementById('status').dataset.kind === 'error'", timeout=timeout)


def code_value(page) -> str:
    """コードタブの内容（タブを開かずに読む）。"""
    return page.evaluate("document.getElementById('customPyCode').value")


def is_hidden_by_id(page, element_id) -> bool:
    """hidden 属性・display:none のどちらでも、画面に出ていない。"""
    return page.evaluate("(id) => { const e = document.getElementById(id); return !e || e.getClientRects().length === 0; }", element_id)


# --- エラーバー（Phase 5a, G1） ---
def eb_id(series_id, direction, name):
    """エラーバーの入力欄の id。direction は y / x、name は mode / symmetric / value / value-minus / column / column-minus。"""
    return f"#series-{series_id}-{direction}err-{name}"


def set_errorbars(
    page, series_id, direction, *, mode=None, symmetric=None, value=None, value_minus=None, column=None, column_minus=None
):
    """系列のエラーバーの入力欄を順に変える（待たない。呼び出し側が wait_settled などで待つ）。
    折りたたみが閉じていれば開く（開く操作は設定を変えない）。"""
    page.evaluate("(id) => { document.getElementById(`series-${id}-errorbars`).open = true; }", series_id)
    if mode is not None:
        page.select_option(eb_id(series_id, direction, "mode"), mode)
    if symmetric is not None:
        page.set_checked(eb_id(series_id, direction, "symmetric"), bool(symmetric))
    if value is not None:
        page.fill(eb_id(series_id, direction, "value"), str(value))
    if value_minus is not None:
        page.fill(eb_id(series_id, direction, "value-minus"), str(value_minus))
    if column is not None:
        page.select_option(eb_id(series_id, direction, "column"), column)
    if column_minus is not None:
        page.select_option(eb_id(series_id, direction, "column-minus"), column_minus)


def error_bar_count(page, axis_index=0) -> int:
    """表示中の図の、エラーバーの数（data-summary の errorbars）。"""
    return image_summary(page)[axis_index]["errorbars"]


def series_errorbars(page, series_id) -> dict:
    """画面の状態（state）にある系列の errorBars。"""
    return page.evaluate(
        "(id) => import(new URL('js/state.js', document.baseURI)).then((m) => m.getSettings().series.find((s) => s.id === id).errorBars)",
        series_id,
    )


# --- 系列のスタイル・注釈・近似曲線（Phase 5b） ---
def series_ids(page) -> list[str]:
    """画面の系列カードの順（id）。"""
    return page.eval_on_selector_all("#seriesList .series-item", "els => els.map(e => e.dataset.seriesId)")


def series_state(page, series_id) -> dict:
    """画面の状態（state）にある系列の設定。"""
    return page.evaluate(
        "(id) => import(new URL('js/state.js', document.baseURI)).then((m) => m.getSettings().series.find((s) => s.id === id))",
        series_id,
    )


def state_list(page, key) -> list[dict]:
    """state の annotations / fits。"""
    return page.evaluate("(k) => import(new URL('js/state.js', document.baseURI)).then((m) => m.getSettings()[k])", key)


def set_fill(page, series_id, *, lower=None, upper=None, alpha=None):
    """塗りつぶし帯の入力欄を変える（折りたたみが閉じていれば開く。待たない）。"""
    page.evaluate("(id) => { document.getElementById(`series-${id}-fill`).open = true; }", series_id)
    if lower is not None:
        page.select_option(f"#series-{series_id}-fill-lower", lower)
    if upper is not None:
        page.select_option(f"#series-{series_id}-fill-upper", upper)
    if alpha is not None:
        page.fill(f"#series-{series_id}-fill-alpha", str(alpha))


def set_card_field(page, selector, value):
    """カード内の入力欄を、種類に応じて変える（select は選択、checkbox は切替、それ以外は入力）。待たない。"""
    kind = page.evaluate(
        "(s) => { const e = document.querySelector(s); return e.type === 'checkbox' ? 'checkbox' : e.tagName.toLowerCase(); }", selector
    )
    if kind == "checkbox":
        page.set_checked(selector, bool(value))
    elif kind == "select":
        page.select_option(selector, value)
    else:
        page.fill(selector, str(value))


def add_annotation(page, kind="hline", **fields) -> str:
    """「+ 注釈を追加」を押し、種類と入力欄（text / coords / x / y / start / end / axis / line-style / line-width / alpha / font-size / label）を設定して id を返す。待たない。"""
    before = {a["id"] for a in state_list(page, "annotations")}
    page.click("#addAnnotationBtn")
    new = [a["id"] for a in state_list(page, "annotations") if a["id"] not in before][0]
    page.select_option(f"#annotation-{new}-kind", kind)
    for name, value in fields.items():
        set_card_field(page, f"#annotation-{new}-{name.replace('_', '-')}", value)
    return new


def set_annotation(page, ann_id, **fields):
    for name, value in fields.items():
        set_card_field(page, f"#annotation-{ann_id}-{name.replace('_', '-')}", value)


def add_fit(page, **fields) -> str:
    """「+ 近似曲線を追加」を押し、入力欄（series / model / degree / show / color / line-style）を設定して id を返す。待たない。"""
    before = {f["id"] for f in state_list(page, "fits")}
    page.click("#addFitBtn")
    new = [f["id"] for f in state_list(page, "fits") if f["id"] not in before][0]
    for name, value in fields.items():
        set_card_field(page, f"#fit-{new}-{name.replace('_', '-')}", value)
    return new


# --- グラフの種類（Phase 5c, G7） ---
def set_plot_type(page, plot_type):
    """プロット種別を変え、読込・描画が一段落するまで待つ（エラー終了を含む）。"""
    page.select_option("#plotType", plot_type)
    wait_settled(page)


def plot_settings(page) -> dict:
    """state の plot 設定（隠した設定の値が残っているかの確認に使う）。"""
    return page.evaluate("import(new URL('js/state.js', document.baseURI)).then((m) => m.getSettings().plot)")


def visible_ids(page, ids) -> dict:
    """要素 id → 画面に出ているか。"""
    return {i: not is_hidden_by_id(page, i) for i in ids}


# --- 計算した列（Phase 5c, G6） ---
def add_computed(page, expr="", name="", source=None) -> str:
    """「+ 列を追加」を押し、名前・式・データ元を入力して id（c1…）を返す。待たない。"""
    before = {c["id"] for c in state_list(page, "computed")}
    page.click("#addComputedBtn")
    new = [c["id"] for c in state_list(page, "computed") if c["id"] not in before][0]
    if source is not None:
        page.select_option(f"#computed-{new}-source", source)
    if name:
        page.fill(f"#computed-{new}-name", name)
    if expr:
        page.fill(f"#computed-{new}-expr", expr)
    return new


def computed_index_text(page, computed_id) -> str:
    return page.inner_text(f"#computed-{computed_id}-index")


def option_labels(page, select_id) -> dict:
    """select の option の value → 表示。"""
    return page.evaluate(
        "(id) => Object.fromEntries([...document.querySelectorAll(`#${id} option`)].map(o => [o.value, o.textContent.trim()]))", select_id
    )
