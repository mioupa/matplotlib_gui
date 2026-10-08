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
    enter_edit_mode, image_generation, load_fixture, plot_src,
    set_save_dpi, wait_app_ready, wait_copy_state, wait_data_ready, wait_latin_state,
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


def fmt(name, xs):
    s = stats(xs)
    return f"{name:<44} median {s['median']:9.0f}  min {s['min']:9.0f}  max {s['max']:9.0f}  (ms, n={s['n']})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    serve = Path(os.environ.get("E2E_SERVE_DIR") or REPO)
    srv, url = start_server(serve)
    tmp = Path(tempfile.mkdtemp(prefix="bench_"))
    csv_path = tmp / "bench_10000x6.csv"
    make_csv(csv_path)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.headed)
        print("chromium", browser.version, "headed" if a.headed else "headless", "platform", platform.platform())
        cold, warm = bench_startup(browser, url, a.reps)
        first, change, save, edit_run = bench_render(browser, url, a.reps, csv_path)
        xlsx = bench_xlsx(browser, url, a.reps, REPO / "tests" / "fixtures" / "multi_sheet.xlsx")
        save120, save300 = bench_save_dpi(browser, url, a.reps, csv_path)
        latin_first, latin_cached, latin_fetch = bench_latin_font(browser, url, a.reps, csv_path)
        copy = bench_copy(browser, url, a.reps, csv_path)
        jp_total, jp_after_ready = bench_japanese_font(browser, url, a.reps)
        browser.close()
    res = {
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
    }
    for k, v in res.items():
        print(fmt(k, v))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=1))
    srv.shutdown()


if __name__ == "__main__":
    main()
