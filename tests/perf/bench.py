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
from helpers import load_fixture, plot_src, wait_app_ready, wait_data_ready, wait_plot_changed  # noqa: E402
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
    first_plot, change, save = [], [], []
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
        page.close()
    ctx.close()
    return first_plot, change, save


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
        first, change, save = bench_render(browser, url, a.reps, csv_path)
        xlsx = bench_xlsx(browser, url, a.reps, REPO / "tests" / "fixtures" / "multi_sheet.xlsx")
        browser.close()
    res = {
        "cold_startup_ms": cold, "warm_startup_ms": warm,
        "first_plot_ms": first, "change_to_plot_ms": change,
        "change_to_plot_minus_debounce_ms": [c - DEBOUNCE_MS for c in change],
        "save_png_ms": save,
        "first_xlsx_plot_ms": xlsx,
    }
    for k, v in res.items():
        print(fmt(k, v))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=1))
    srv.shutdown()


if __name__ == "__main__":
    main()
