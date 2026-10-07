// Python 起動中の進み具合を、ブラウザが観測できるもの（Resource Timing）から段階として推定する。
// PyScript 2026.7.3 にはパッケージ読込の進捗 API が無い。リソースのエントリは取得完了時に追加され、
// HTTP キャッシュからの取得でもエントリは作られる（その場合は段階が短時間で進むだけ）。
// 段階: runtime（Pyodide 本体）→ packages（pandas / matplotlib などの wheel）→ init（import・初期化）。段階は戻らない。
const RUNTIME_FILES = ["pyodide.asm.wasm", "python_stdlib.zip"];
const TRACKED_PACKAGES = ["pandas", "matplotlib"]; // pyscript.toml の packages と揃える
const PYODIDE_PATH = "/pyodide/v"; // Pyodide 本体と同梱パッケージの配置（Excel 用 wheel は対象外）
const ENTRY_POINT = "/py/main.py"; // PyScript が main.py を取得した＝パッケージ導入が終わり、import・初期化に入った

export const RUNTIME_MESSAGE = "Python 実行環境を読み込み中…（初回は時間がかかります）";
export const INIT_MESSAGE = "ライブラリを初期化中…";

export const packagesMessage = (done) =>
  `ライブラリを読み込み中…（${TRACKED_PACKAGES.map((n) => `${n} ${done.has(n) ? "✓" : "…"}`).join(", ")}）`;

// onChange(stage, message) を、段階またはメッセージが変わるたびに呼ぶ。戻り値は停止関数。
export const watchStartup = (onChange) => {
  if (typeof PerformanceObserver === "undefined") return () => {};
  const runtimeSeen = new Set();
  const packagesDone = new Set();
  let entrySeen = false;
  let stage = "runtime";
  let last = "";
  const compute = () => {
    let next = "runtime";
    if (RUNTIME_FILES.every((f) => runtimeSeen.has(f))) next = "packages";
    if (entrySeen || (next === "packages" && TRACKED_PACKAGES.every((n) => packagesDone.has(n)))) next = "init";
    const order = ["runtime", "packages", "init"];
    if (order.indexOf(next) > order.indexOf(stage)) stage = next;
    const message = stage === "runtime" ? RUNTIME_MESSAGE : stage === "packages" ? packagesMessage(packagesDone) : INIT_MESSAGE;
    if (message !== last) {
      last = message;
      onChange(stage, message);
    }
  };
  const handle = (entries) => {
    for (const entry of entries) {
      const url = entry.name.split("?")[0];
      if (url.endsWith(ENTRY_POINT)) entrySeen = true;
      if (!url.includes(PYODIDE_PATH)) continue;
      const file = url.slice(url.lastIndexOf("/") + 1);
      if (RUNTIME_FILES.includes(file)) runtimeSeen.add(file);
      else if (file.endsWith(".whl")) packagesDone.add(file.split("-")[0].toLowerCase().replace(/_/g, "-"));
    }
    compute();
  };
  const observer = new PerformanceObserver((list) => handle(list.getEntries()));
  observer.observe({ type: "resource", buffered: true }); // 既に記録済みのエントリも受け取る
  return () => observer.disconnect();
};
