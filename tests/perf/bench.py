"""ベースライン/比較用ベンチマーク（pytest では収集されない: test_ で始まらない）。

実行: uv run python tests/perf/bench.py [--reps 5] [--headed] [--json out.json]
E2E_SERVE_DIR で配信ディレクトリを切り替えられる（既定: リポジトリルート）。
アプリ固有の待機は tests/e2e/helpers.py を再利用する。
"""
import argparse
import csv
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "e2e"))
from helpers import (  # noqa: E402
    add_series_with_source, enter_edit_mode, image_generation, load_fixture, paste_text, plot_src,
    add_annotation, add_computed, add_fit, series_ids, set_fill, open_tick_group, set_axis_option, set_errorbars, set_save_dpi, wait_app_ready, wait_copy_state, wait_data_ready, wait_latin_state,
    wait_plot_changed,
)
from server import start_server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

DEBOUNCE_MS = 250
TIMEOUT = 300_000

# 変更イベント発行から新しい画像表示までを、ページ内の performance.now() で測る
CHANGE_JS = """
([sel, value]) => new Promise((resolve) => {
  const area = document.getElementById('plotArea');
  const prev = (area.querySelector('img') || {}).src || '';
  const el = document.querySelector(sel);
  const t0 = performance.now();
  const check = () => {
    const s = (area.querySelector('img') || {}).src || '';
    if (s && s !== prev) { obs.disconnect(); resolve(performance.now() - t0); }
  };
  const obs = new MutationObserver(check);
  obs.observe(area, {childList: true, subtree: true, attributes: true});
  el.value = value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
});
"""


def stats(xs):
    return {"median": statistics.median(xs), "min": min(xs), "max": max(xs), "n": len(xs)}


def make_csv(path, rows=10_000):
    import math
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x", "y1", "y2", "y3", "y4", "y5"])
        for i in range(rows):
            x = i * 0.01
            w.writerow([round(x, 4)] + [round(math.sin(x * (k + 1)) + 0.1 * k, 5) for k in range(5)])


def setup_series(page):
    for _ in range(4):
        page.click("#addSeriesBtn")
    n = page.locator("#seriesList .series-item").count()
    assert n == 5, n
    for k in range(5):
        item = page.locator("#seriesList .series-item").nth(k)
        item.locator(".series-x").select_option("__idx__0")
        item.locator(".series-y").select_option(f"__idx__{k + 1}")


def bench_startup(browser, url, reps):
    cold, warm = [], []
    for _ in range(reps):
        ctx = browser.new_context()  # 空のHTTPキャッシュ
        page = ctx.new_page()
        t = time.perf_counter()
        page.goto(url, timeout=TIMEOUT)
        wait_app_ready(page, TIMEOUT)
        cold.append((time.perf_counter() - t) * 1000)
        ctx.close()
    # ウォーム: 同一コンテキストで1回目(捨てる)の後、新規ページで再ナビゲート（HTTPキャッシュ有効）
    ctx = browser.new_context()
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    p0.close()
    for _ in range(reps):
        page = ctx.new_page()
        t = time.perf_counter()
        page.goto(url, timeout=TIMEOUT)
        wait_app_ready(page, TIMEOUT)
        warm.append((time.perf_counter() - t) * 1000)
        page.close()
    ctx.close()
    return cold, warm


def bench_render(browser, url, reps, csv_path):
    first_plot, change, save, edit_run = [], [], [], []
    ctx = browser.new_context()
    # フォント等をHTTPキャッシュに載せるための捨て試行
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    load_fixture(p0, csv_path)
    wait_plot_changed(p0, "", TIMEOUT)
    p0.close()
    for i in range(reps):
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t = time.perf_counter()
        page.set_input_files("#fileInput", str(csv_path))
        wait_data_ready(page, TIMEOUT)
        wait_plot_changed(page, "", TIMEOUT)
        first_plot.append((time.perf_counter() - t) * 1000)
        setup_series(page)
        page.wait_for_timeout(3000)  # 系列設定による再描画の収束待ち
        src = plot_src(page)
        change.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.wait_for_timeout(1500)
        t = time.perf_counter()
        with page.expect_download(timeout=TIMEOUT) as dl:
            page.click("#savePlotBtn")
        dl.value.path()
        save.append((time.perf_counter() - t) * 1000)
        # 編集モードでの実行（Phase 2 で追加。保存の後に測るので既存の項目には影響しない）。
        # Ctrl/Cmd+Enter から新しい画像の表示まで（ファイルの再読込とスクリプト全体の実行を含む）
        page.wait_for_timeout(1000)
        enter_edit_mode(page)
        page.wait_for_timeout(1500)
        page.focus("#customPyCode")
        prev = image_generation(page)
        t = time.perf_counter()
        page.keyboard.press("ControlOrMeta+Enter")
        page.wait_for_function(
            """(prev) => {
              const d = document.documentElement.dataset;
              const img = document.querySelector('#plotArea img');
              return d.renderState === 'idle' && !!img && img.dataset.generation !== prev;
            }""",
            arg=prev, timeout=TIMEOUT,
        )
        edit_run.append((time.perf_counter() - t) * 1000)
        page.close()
    ctx.close()
    return first_plot, change, save, edit_run


def bench_xlsx(browser, url, reps, xlsx_path):
    """初回の .xlsx 読込 → 最初のプロット（Excel 用 wheel の遅延取得を含む。HTTP キャッシュは温めた状態）。"""
    out = []
    ctx = browser.new_context()
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    load_fixture(p0, xlsx_path)
    wait_plot_changed(p0, "", TIMEOUT)
    p0.close()
    for _ in range(reps):
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t = time.perf_counter()
        page.set_input_files("#fileInput", str(xlsx_path))
        wait_data_ready(page, TIMEOUT)
        wait_plot_changed(page, "", TIMEOUT)
        out.append((time.perf_counter() - t) * 1000)
        page.close()
    ctx.close()
    return out


def _prepared_page(ctx, url, csv_path):
    """新規ページで起動 → 10,000 行の CSV を読込 → 系列5本を設定 → 描画の収束を待つ。"""
    page = ctx.new_page()
    page.set_default_timeout(TIMEOUT)
    page.goto(url)
    wait_app_ready(page, TIMEOUT)
    page.set_input_files("#fileInput", str(csv_path))
    wait_data_ready(page, TIMEOUT)
    wait_plot_changed(page, "", TIMEOUT)
    setup_series(page)
    page.wait_for_timeout(3000)
    return page


def _warm_context(browser, url, csv_path, **kw):
    """HTTP キャッシュ・Cache Storage（日本語フォント）を温めたコンテキスト。"""
    ctx = browser.new_context(**kw)
    _prepared_page(ctx, url, csv_path).close()
    return ctx


def bench_save_dpi(browser, url, reps, csv_path):
    """Phase 3: 保存 PNG を 120 dpi（Phase 2 の固定値。「保存」と直接比較できる）と 300 dpi（既定）で測る。
    測り方は bench_render の「保存」と同じ（クリック → ダウンロード開始）。"""
    save120, save300 = [], []
    ctx = _warm_context(browser, url, csv_path)
    for dpi, out in ((120, save120), (300, save300)):
        for _ in range(reps):
            page = _prepared_page(ctx, url, csv_path)
            if dpi != 300:
                set_save_dpi(page, dpi)
            page.wait_for_timeout(1500)
            t = time.perf_counter()
            with page.expect_download(timeout=TIMEOUT) as dl:
                page.click("#savePlotBtn")
            dl.value.path()
            out.append((time.perf_counter() - t) * 1000)
            page.close()
    ctx.close()
    return save120, save300


def bench_copy(browser, url, reps, csv_path):
    """Phase 3: #copyPlotBtn のクリック → data-copy-state が done（既定 300 dpi）。"""
    out = []
    ctx = _warm_context(browser, url, csv_path, permissions=["clipboard-read", "clipboard-write"])
    for _ in range(reps):
        page = _prepared_page(ctx, url, csv_path)
        page.wait_for_timeout(1500)
        t = time.perf_counter()
        page.click("#copyPlotBtn")
        wait_copy_state(page, "done", TIMEOUT)
        out.append((time.perf_counter() - t) * 1000)
        page.close()
    ctx.close()
    return out


def bench_latin_font(browser, url, reps, csv_path):
    """Phase 3: 欧文フォント（Arimo）の選択 → 新しい画像の表示。「設定変更」と同じ CHANGE_JS で測る
    （select の input イベント発行から。250 ms のデバウンスを含む）。
    (a) 初回: 反復ごとに新規コンテキスト（Cache Storage も HTTP キャッシュも空）で jsDelivr から実取得。
    (b) 2回目以降: Cache Storage に Arimo がある状態（同一コンテキストで1回選んで保存済み）。"""
    first, cached, first_fetch = [], [], []
    for _ in range(reps):
        ctx = browser.new_context()
        page = _prepared_page(ctx, url, csv_path)
        page.wait_for_timeout(1500)
        # 参考: 選択から data-latin-font-state が ready になるまで（取得 + 登録。デバウンスと並行して進む）
        page.evaluate("""() => {
          const root = document.documentElement;
          window.__latinReady = new Promise((resolve) => {
            const t0 = performance.now();
            const obs = new MutationObserver(() => {
              if (root.dataset.latinFontState === 'ready') { obs.disconnect(); resolve(performance.now() - t0); }
            });
            obs.observe(root, {attributes: true});
          });
        }""")
        first.append(page.evaluate(CHANGE_JS, ["#latinFont", "arimo"]))
        first_fetch.append(page.evaluate("window.__latinReady"))
        ctx.close()
    ctx = browser.new_context()
    page = _prepared_page(ctx, url, csv_path)
    page.evaluate(CHANGE_JS, ["#latinFont", "arimo"])
    wait_latin_state(page, "ready", TIMEOUT)
    page.close()
    for _ in range(reps):
        page = _prepared_page(ctx, url, csv_path)
        page.wait_for_timeout(1500)
        cached.append(page.evaluate(CHANGE_JS, ["#latinFont", "arimo"]))
        wait_latin_state(page, "ready", TIMEOUT)
        page.close()
    ctx.close()
    return first, cached, first_fetch


def bench_japanese_font(browser, url, reps):
    """Phase 3（新規）: コールドキャッシュでの日本語フォント取得。ナビゲーション開始 → data-font-state が ready、
    および Python 準備完了（app ready）からの追加待ち時間。"""
    total, after_ready = [], []
    for _ in range(reps):
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        t = time.perf_counter()
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t_ready = time.perf_counter()
        page.wait_for_function("document.documentElement.dataset.fontState === 'ready'", timeout=TIMEOUT)
        t_font = time.perf_counter()
        total.append((t_font - t) * 1000)
        after_ready.append((t_font - t_ready) * 1000)
        ctx.close()
    return total, after_ready


# --- Phase 4: データ読込の追加機能（貼り付け・シート切替・日時・複数ファイル） ---
# シートの切り替えは change イベント（select）。測り方は CHANGE_JS と同じ。
SHEET_JS = CHANGE_JS.replace("'input'", "'change'")


def make_tsv(rows=10_000, ys=5):
    import math
    lines = ["\t".join(["x"] + [f"y{k + 1}" for k in range(ys)])]
    for i in range(rows):
        x = i * 0.01
        lines.append("\t".join([str(round(x, 4))] + [str(round(math.sin(x * (k + 1)) + 0.1 * k, 5)) for k in range(ys)]))
    return "\r\n".join(lines) + "\r\n"


def make_xlsx(path, rows=10_000, sheets=2):
    import math
    from openpyxl import Workbook
    wb = Workbook(write_only=True)
    for s in range(sheets):
        ws = wb.create_sheet(f"シート{s + 1}")
        ws.append(["x", "y1", "y2", "y3", "y4", "y5"])
        for i in range(rows):
            x = i * 0.01
            ws.append([round(x, 4)] + [round(math.sin(x * (k + 1) + s) + 0.1 * k, 5) for k in range(5)])
    wb.save(path)


def make_datetime_csv(path, rows=10_000):
    import datetime
    import math
    t0 = datetime.datetime(2026, 1, 1)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "y1", "y2", "y3", "y4", "y5"])
        for i in range(rows):
            x = i * 0.01
            t = t0 + datetime.timedelta(seconds=30 * i)
            w.writerow([t.strftime("%Y/%m/%d %H:%M:%S")] + [round(math.sin(x * (k + 1)) + 0.1 * k, 5) for k in range(5)])


def bench_paste(browser, url, reps, big_text, small_text):
    """貼り付け（ClipboardEvent を #pasteArea へ）→ 最初のプロット。終了条件は「初回ファイル読込」と同じ。"""
    out = {}
    ctx = browser.new_context()
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    paste_text(p0, small_text)
    wait_data_ready(p0, TIMEOUT)
    wait_plot_changed(p0, "", TIMEOUT)
    p0.close()
    for name, text in (("paste_10000x6_first_plot_ms", big_text), ("paste_small_30rows_first_plot_ms", small_text)):
        out[name] = []
        for _ in range(reps):
            page = ctx.new_page()
            page.set_default_timeout(TIMEOUT)
            page.goto(url)
            wait_app_ready(page, TIMEOUT)
            t = time.perf_counter()
            paste_text(page, text)
            wait_data_ready(page, TIMEOUT)
            wait_plot_changed(page, "", TIMEOUT)
            out[name].append((time.perf_counter() - t) * 1000)
            page.close()
    ctx.close()
    return out


def bench_sheet_switch(browser, url, reps, xlsx_path):
    """2 シート × 10,000 行の xlsx。(a) 初回読込 → 最初のプロット（Excel 用 wheel 取得込み、HTTP キャッシュは温めた状態）、
    (b) 系列5本を設定した後、#sheetSelect で 2 枚目へ → 新しい画像（change イベントから。読み直し + 描画）。"""
    first, switch = [], []
    ctx = browser.new_context()
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    load_fixture(p0, xlsx_path)
    wait_plot_changed(p0, "", TIMEOUT)
    p0.close()
    for _ in range(reps):
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t = time.perf_counter()
        page.set_input_files("#fileInput", str(xlsx_path))
        wait_data_ready(page, TIMEOUT)
        wait_plot_changed(page, "", TIMEOUT)
        first.append((time.perf_counter() - t) * 1000)
        setup_series(page)  # 既定の系列は X 列そのものを描くので、シートで絵が変わるよう 5 系列にしておく
        page.wait_for_timeout(3000)
        switch.append(page.evaluate(SHEET_JS, ["#sheetSelect", "シート2"]))
        page.close()
    ctx.close()
    return first, switch


def bench_datetime(browser, url, reps, dt_path):
    """日時の列（%Y/%m/%d %H:%M:%S）+ 数値5列、10,000 行。X = 日時の列、系列5本。"""
    first, change = [], []
    ctx = _warm_context(browser, url, dt_path)
    for i in range(reps):
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t = time.perf_counter()
        page.set_input_files("#fileInput", str(dt_path))
        wait_data_ready(page, TIMEOUT)
        wait_plot_changed(page, "", TIMEOUT)
        first.append((time.perf_counter() - t) * 1000)
        setup_series(page)
        page.wait_for_timeout(3000)
        change.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return first, change


def bench_two_files(browser, url, reps, path1, path2):
    """2つの 10,000 行 CSV を #fileInput（multiple）で同時に選ぶ → 最初のプロット。
    設定変更: 系列1 はファイル1、系列2 はファイル2 の 2 系列でタイトルを変える。"""
    first, change = [], []
    ctx = browser.new_context()
    p0 = ctx.new_page()
    p0.goto(url, timeout=TIMEOUT)
    wait_app_ready(p0, TIMEOUT)
    p0.set_input_files("#fileInput", [str(path1), str(path2)])
    wait_data_ready(p0, TIMEOUT)
    wait_plot_changed(p0, "", TIMEOUT)
    p0.close()
    for i in range(reps):
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)
        wait_app_ready(page, TIMEOUT)
        t = time.perf_counter()
        page.set_input_files("#fileInput", [str(path1), str(path2)])
        wait_data_ready(page, TIMEOUT)
        wait_plot_changed(page, "", TIMEOUT)
        first.append((time.perf_counter() - t) * 1000)
        page.wait_for_timeout(2000)
        add_series_with_source(page, "d2", y="__idx__1", series_id="s2")
        page.wait_for_timeout(3000)
        change.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return first, change


# --- Phase 5a: エラーバー・目盛の設定変更 ---
def make_errorbar_csv(path, rows=10_000):
    """X + Y 5列 + 誤差 5列（正の値）= 11 列。"""
    import math
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x"] + [f"y{k + 1}" for k in range(5)] + [f"e{k + 1}" for k in range(5)])
        for i in range(rows):
            x = i * 0.01
            w.writerow(
                [round(x, 4)]
                + [round(math.sin(x * (k + 1)) + 0.1 * k, 5) for k in range(5)]
                + [round(0.05 + 0.02 * abs(math.cos(x * (k + 1))), 5) for k in range(5)]
            )


def bench_errorbar_change(browser, url, reps, eb_path):
    """5 系列（Y = 列1-5）すべてに Y 誤差（列モード・対称、誤差列 6-10）を設定し、画像に errorbars が 5 になるまで待ってから、
    既存の「設定変更」と同じ方法（タイトルの input → 新しい画像。デバウンス込み）で測る。"""
    out = []
    ctx = _warm_context(browser, url, eb_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, eb_path)
        ids = page.evaluate("[...document.querySelectorAll('#seriesList .series-item')].map(e => e.querySelector('.series-y').id.match(/^series-(.+)-y$/)[1])")
        assert len(ids) == 5, ids
        for k, sid in enumerate(ids):
            set_errorbars(page, sid, "y", mode="column", column=f"__idx__{k + 6}")
        page.wait_for_function(
            """() => { const d = document.querySelector('#plotArea img'); if (!d || !d.dataset.summary) return false;
              try { return JSON.parse(d.dataset.summary)[0].errorbars >= 5; } catch (e) { return false; } }""",
            timeout=TIMEOUT)
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


def bench_ticks_change(browser, url, reps, csv_path):
    """目盛の設定: Y 主目盛の間隔 0.2（約 10 本）、Y 副目盛 表示・分割 5、Y 目盛の書式 小数 2 桁、X 反転、上・右の枠線なし。"""
    out = []
    ctx = _warm_context(browser, url, csv_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, csv_path)
        open_tick_group(page, "x")
        open_tick_group(page, "y")
        for sel, val in (("#yMajorStep", "0.2"), ("#yMinorTicks", "on"), ("#yMinorDivisions", "5"),
                         ("#yTickFormat", "fixed"), ("#yTickDecimals", "2"), ("#xInverted", True),
                         ("#spineTop", False), ("#spineRight", False)):
            set_axis_option(page, sel, val)
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


# --- Phase 5b: 塗りつぶし帯・近似曲線・注釈 ---
def make_band_csv(path, rows=10_000):
    """X + Y 5列 + 帯の下端 5列 + 帯の上端 5列 = 16 列。"""
    import math
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x"] + [f"y{k + 1}" for k in range(5)] + [f"lo{k + 1}" for k in range(5)] + [f"hi{k + 1}" for k in range(5)])
        for i in range(rows):
            x = i * 0.01
            ys = [math.sin(x * (k + 1)) + 0.1 * k for k in range(5)]
            w.writerow([round(x, 4)] + [round(y, 5) for y in ys] + [round(y - 0.2, 5) for y in ys] + [round(y + 0.2, 5) for y in ys])


def bench_p5b_change(browser, url, reps, band_path):
    """5 系列すべてに塗りつぶし帯（下端 列6-10、上端 列11-15）と1次の近似曲線（凡例）を付け、注釈3つ（水平線・縦の帯・文字）を置き、
    data-summary に帯 5・近似線 5・注釈が出るまで待ってから、既存の「設定変更」と同じ方法で測る。"""
    out = []
    ctx = _warm_context(browser, url, band_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, band_path)
        ids = page.evaluate("[...document.querySelectorAll('#seriesList .series-item')].map(e => e.querySelector('.series-y').id.match(/^series-(.+)-y$/)[1])")
        assert len(ids) == 5, ids
        for k, sid in enumerate(ids):
            set_fill(page, sid, lower=f"__idx__{k + 6}", upper=f"__idx__{k + 11}")
            add_fit(page, series=sid)
        add_annotation(page, "hline", y="0.5")
        add_annotation(page, "vspan", start="20", end="30")
        add_annotation(page, "text", text="bench", x="50", y="1")
        page.wait_for_function(
            """() => { const d = document.querySelector('#plotArea img'); if (!d || !d.dataset.summary) return false;
              try { const s = JSON.parse(d.dataset.summary)[0], a = s.annotations;
                return s.bands >= 5 && s.fitlines >= 5 && a.hlines >= 1 && a.vspans >= 1 && a.texts >= 1; } catch (e) { return false; } }""",
            timeout=TIMEOUT)
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


# --- Phase 5c: 色分け散布図・ヒストグラム・計算した列 ---
def make_color_csv(path, rows=10_000):
    """X + Y 5列 + 色の値 5列 = 11 列。"""
    import math
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x"] + [f"y{k + 1}" for k in range(5)] + [f"c{k + 1}" for k in range(5)])
        for i in range(rows):
            x = i * 0.01
            ys = [math.sin(x * (k + 1)) + 0.1 * k for k in range(5)]
            w.writerow([round(x, 4)] + [round(y, 5) for y in ys] + [round(math.cos(x * (k + 1)) * (k + 1), 5) for k in range(5)])


def _wait_summary(page, cond):
    """表示中の画像の data-summary（最初の Axes）が cond（JS の式。s が要約）を満たすまで待つ。"""
    page.wait_for_function(
        """(cond) => { const d = document.querySelector('#plotArea img'); if (!d || !d.dataset.summary) return false;
          try { const s = JSON.parse(d.dataset.summary)[0]; return Function('s', 'return ' + cond)(s); } catch (e) { return false; } }""",
        arg=cond, timeout=TIMEOUT)


def bench_scatter_color_change(browser, url, reps, color_path):
    """色分け散布図: 5 系列（Y 列1-5、色分けの列 6-10。凡例あり）のカラーバー付きの図が出るまで待ってから、「設定変更」を測る。"""
    out = []
    ctx = _warm_context(browser, url, color_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, color_path)
        page.select_option("#plotType", "scatterColor")
        for k, sid in enumerate(series_ids(page)):
            page.select_option(f"#series-{sid}-color-column", f"__idx__{k + 6}")
        _wait_summary(page, "!!s.colorbar")
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


def bench_hist_change(browser, url, reps, csv_path):
    """ヒストグラム: 5 系列（Y 列1-5、区間は自動）の図が出るまで待ってから、「設定変更」を測る。"""
    out = []
    ctx = _warm_context(browser, url, csv_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, csv_path)
        page.select_option("#plotType", "hist")
        _wait_summary(page, "s.bars && s.bars.containers.length >= 5")
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


def bench_computed_change(browser, url, reps, csv_path):
    """計算した列: 列1-5 をそれぞれ正規化（[k] / max([k])）した計算した列 5 つ（列 [6]-[10]）を、line 5 系列の Y にした図が出るまで待ってから、
    「設定変更」を測る。"""
    out = []
    ctx = _warm_context(browser, url, csv_path)
    for i in range(reps):
        page = _prepared_page(ctx, url, csv_path)
        for k in range(1, 6):
            add_computed(page, expr=f"[{k}] / max([{k}])")
        for k, sid in enumerate(series_ids(page)):
            page.select_option(f"#series-{sid}-y", f"__idx__{k + 6}")
        page.wait_for_function(
            "() => { const c = document.querySelector('#customPyCode').value;"
            " return c.includes('計算した列5') && c.includes('df.iloc[:, 10]'); }",
            timeout=TIMEOUT)
        page.wait_for_timeout(3000)
        out.append(page.evaluate(CHANGE_JS, ["#title", f"bench title {i}"]))
        page.close()
    ctx.close()
    return out


def fmt(name, xs):
    s = stats(xs)
    return f"{name:<44} median {s['median']:9.0f}  min {s['min']:9.0f}  max {s['max']:9.0f}  (ms, n={s['n']})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--only", choices=["old", "new", "p5a", "p5b", "p5c"], help="old: Phase 3 までの項目だけ / new: Phase 4 の項目だけ / p5a: Phase 5a の項目だけ / p5b: Phase 5b の項目だけ / p5c: Phase 5c の項目だけ（省略時は全部）")
    a = ap.parse_args()
    serve = Path(os.environ.get("E2E_SERVE_DIR") or REPO)
    srv, url = start_server(serve)
    tmp = Path(tempfile.mkdtemp(prefix="bench_"))
    csv_path = tmp / "bench_10000x6.csv"
    make_csv(csv_path)
    csv2_path = tmp / "bench_10000x6_b.csv"
    make_csv(csv2_path)
    xlsx_path = tmp / "bench_2sheets_10000x6.xlsx"
    make_xlsx(xlsx_path)
    dt_path = tmp / "bench_datetime_10000x6.csv"
    make_datetime_csv(dt_path)
    eb_path = tmp / "bench_errorbars_10000x11.csv"
    make_errorbar_csv(eb_path)
    band_path = tmp / "bench_bands_10000x16.csv"
    make_band_csv(band_path)
    color_path = tmp / "bench_color_10000x11.csv"
    make_color_csv(color_path)
    big_tsv = make_tsv()
    small_tsv = make_tsv(rows=30, ys=2)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.headed)
        print("chromium", browser.version, "headed" if a.headed else "headless", "platform", platform.platform())
        res = {}
        if a.only in (None, "old"):
            cold, warm = bench_startup(browser, url, a.reps)
            first, change, save, edit_run = bench_render(browser, url, a.reps, csv_path)
            xlsx = bench_xlsx(browser, url, a.reps, REPO / "tests" / "fixtures" / "multi_sheet.xlsx")
            save120, save300 = bench_save_dpi(browser, url, a.reps, csv_path)
            latin_first, latin_cached, latin_fetch = bench_latin_font(browser, url, a.reps, csv_path)
            copy = bench_copy(browser, url, a.reps, csv_path)
            jp_total, jp_after_ready = bench_japanese_font(browser, url, a.reps)
            res.update({
                "cold_startup_ms": cold, "warm_startup_ms": warm,
                "first_plot_ms": first, "change_to_plot_ms": change,
                "change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in change],
                "save_png_ms": save,
                "edit_mode_run_ms": edit_run,
                "first_xlsx_plot_ms": xlsx,
                # Phase 3 で追加。save_png_ms は既定 300 dpi（Phase 2 までは 120 dpi 固定）
                "save_png_120dpi_ms": save120,
                "save_png_300dpi_ms": save300,
                "latin_font_first_select_to_plot_ms": latin_first,
                "latin_font_cached_select_to_plot_ms": latin_cached,
                "latin_font_first_select_to_font_ready_ms": latin_fetch,  # 参考値
                "copy_to_clipboard_300dpi_ms": copy,
                "japanese_font_cold_navigate_to_font_ready_ms": jp_total,
                "japanese_font_cold_after_app_ready_ms": jp_after_ready,
            })
        if a.only in (None, "new"):
            paste = bench_paste(browser, url, a.reps, big_tsv, small_tsv)
            xlsx_first, sheet_switch = bench_sheet_switch(browser, url, a.reps, xlsx_path)
            dt_first, dt_change = bench_datetime(browser, url, a.reps, dt_path)
            two_first, two_change = bench_two_files(browser, url, a.reps, csv_path, csv2_path)
            res.update({
                # Phase 4 で追加
                **paste,
                "xlsx_2sheets_10000_first_plot_ms": xlsx_first,
                "xlsx_sheet_switch_to_plot_ms": sheet_switch,
                "datetime_10000_first_plot_ms": dt_first,
                "datetime_change_to_plot_ms": dt_change,
                "datetime_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in dt_change],
                "two_files_first_plot_ms": two_first,
                "two_files_change_to_plot_ms": two_change,
                "two_files_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in two_change],
            })
        if a.only in (None, "p5a"):
            eb_change = bench_errorbar_change(browser, url, a.reps, eb_path)
            tk_change = bench_ticks_change(browser, url, a.reps, csv_path)
            res.update({
                # Phase 5a で追加（デバウンス込みと、250 ms を除いた値）
                "errorbar_change_to_plot_ms": eb_change,
                "errorbar_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in eb_change],
                "ticks_change_to_plot_ms": tk_change,
                "ticks_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in tk_change],
            })
        if a.only in (None, "p5b"):
            b_change = bench_p5b_change(browser, url, a.reps, band_path)
            res.update({
                # Phase 5b で追加（帯・近似曲線・注釈を付けた設定変更。デバウンス込みと、250 ms を除いた値）
                "p5b_change_to_plot_ms": b_change,
                "p5b_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in b_change],
            })
        if a.only in (None, "p5c"):
            sc_change = bench_scatter_color_change(browser, url, a.reps, color_path)
            hist_change = bench_hist_change(browser, url, a.reps, csv_path)
            comp_change = bench_computed_change(browser, url, a.reps, csv_path)
            res.update({
                # Phase 5c で追加（色分け散布図・ヒストグラム・計算した列。デバウンス込みと、250 ms を除いた値）
                "scatter_color_change_to_plot_ms": sc_change,
                "scatter_color_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in sc_change],
                "hist_change_to_plot_ms": hist_change,
                "hist_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in hist_change],
                "computed_change_to_plot_ms": comp_change,
                "computed_change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in comp_change],
            })
        browser.close()
    for k, v in res.items():
        print(fmt(k, v))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=1))
    srv.shutdown()


if __name__ == "__main__":
    main()
