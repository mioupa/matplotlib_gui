// Python（window.mplgui）との唯一の窓口。設定は JSON 文字列で渡し、結果の JSON を UI へ反映する。
// - 再描画は設定変更の 250ms 後（デバウンス）、読込はファイル/ヘッダ 0ms・区切り文字 450ms。保存設定の変更では再描画しない。
// - 描画要求には世代番号を振る。同時に走る Python 描画は最大1つで、実行中の要求は「やり直し」の印だけ付け、
//   終わったあと最新の設定で1回だけ描画する。古い世代の結果は画像・ステータスに反映しない。
// - Python の起動前に選んだファイル・変えた設定は保持され、起動後に最新の内容で1回読込・描画する。
import { subscribe, toJson, getSettings } from "./state.js";
import { addStickyWarning, setStatus, warningTexts } from "./ui/notify.js";
import { showPlot } from "./ui/plotView.js";
import { applySkipRows, showPreview } from "./ui/dataPreview.js";
import { setColumns } from "./ui/series.js";
import { showEncoding, showFileName } from "./ui/fileInfo.js";
import { setBusy, showProgress } from "./ui/progress.js";
import { FONT_FIRST_RENDER_WAIT_MS, isFontCached, loadFont } from "./font-cache.js";

const RENDER_DELAY_MS = 250;
const LOAD_DELAY_MS = { file: 0, header: 0, delimiter: 450 };
const FONT_FAILED_MESSAGE = "日本語フォントを取得できませんでした。日本語が正しく表示されない場合があります。";
const PYTHON_LOADING_MESSAGE = "Python 実行環境を読み込み中…（初回は時間がかかります）";
const FONT_LOADING_MESSAGE = "日本語フォントを取得中…";

const root = document.documentElement;
let api = null; // window.mplgui（Python 側が登録）
let selectedFile = null;
let dataReady = false;
let renderTimer = null;
let loadTimer = null;
let latestGeneration = 0; // 最後に要求された描画の世代番号
let renderRunning = false;
let renderDirty = false;
let loadSeq = 0;
let loadCount = 0;
let loadWarnings = [];
let customCodeProvider = () => null; // 有効なカスタムコードの文字列、無効なら null
let readyCallbacks = [];
let fontState = "idle"; // idle | loading | ready | failed
let fontPercent = null;
let fontTask = null;
let excelInstalling = false; // 初回の .xlsx 読込前に Excel 用ライブラリを取得中
let excelReady = false;
let fontWaitGaveUp = false; // 最初の描画がフォント待ちを打ち切った（以後は待たない）

const setDataState = (state) => {
  dataReady = state === "ready";
  root.dataset.dataState = state; // none | loading | ready | error
};
const setRenderState = (state) => {
  root.dataset.renderState = state; // idle | pending | rendering
  const busy = state === "rendering";
  setBusy(busy, fontState === "loading" ? FONT_LOADING_MESSAGE : "描画中…");
};
const setFontState = (state) => {
  fontState = state;
  root.dataset.fontState = state;
};

export const isPythonReady = () => api !== null;
export const canAutoRender = () => dataReady;
export const setCustomCodeProvider = (fn) => {
  customCodeProvider = fn;
};

const EXCEL_LOADING_MESSAGE = "Excel 読込用のライブラリを取得中…";

const callPython = (name, ...args) => JSON.parse(api[name](...args));

const reportError = (error) => {
  setStatus(error.message, "error", error.detail || "");
};
const reportException = (err, context) => {
  const detail = `context: ${context}\n${err && err.stack ? err.stack : String(err)}`;
  setStatus("内部エラーが発生しました。もう一度操作してください。", "error", detail);
};

// 進捗バナー: Python 起動中はその旨、起動後はフォント取得の進捗、どちらも無ければ非表示
const refreshProgress = () => {
  if (!api) showProgress(PYTHON_LOADING_MESSAGE);
  else if (excelInstalling) showProgress(EXCEL_LOADING_MESSAGE);
  else if (fontState === "loading") showProgress(fontPercent === null ? FONT_LOADING_MESSAGE : `${FONT_LOADING_MESSAGE} ${fontPercent}%`);
  else showProgress("");
};

const nextPaint = () =>
  new Promise((resolve) => {
    const timer = window.setTimeout(resolve, 60); // 非表示タブでは rAF が来ないため上限を設ける
    window.requestAnimationFrame(() => {
      window.clearTimeout(timer);
      window.setTimeout(resolve, 0);
    });
  });

// ---- 日本語フォント（A6）。取得はセッション中1回。失敗は警告を1度だけ出し、フォールバックフォントで続行する ----
const startFont = () => {
  if (fontTask) return fontTask;
  setFontState("loading");
  fontPercent = null;
  refreshProgress();
  fontTask = (async () => {
    const bytes = await loadFont((p) => {
      fontPercent = p;
      refreshProgress();
    });
    if (!bytes) {
      setFontState("failed");
      addStickyWarning(FONT_FAILED_MESSAGE);
    } else {
      await new Promise((resolve) => onPythonReady(resolve));
      try {
        api.registerFont(bytes);
        setFontState("ready");
        if (fontWaitGaveUp) renderNow(); // フォント無しで描いた図を、現在の設定で1回だけ描き直す（通常の合流処理・新しい世代）
      } catch (_) {
        setFontState("failed");
        addStickyWarning(FONT_FAILED_MESSAGE);
      }
    }
    fontPercent = null;
    refreshProgress();
    setBusy(root.dataset.renderState === "rendering");
  })();
  return fontTask;
};

// 最初の描画は最大 FONT_FIRST_RENDER_WAIT_MS だけ待つ。超えたらフォールバックフォントで描き、取得完了後に再描画する。
const waitForFont = async () => {
  if (fontState !== "loading" || !fontTask || fontWaitGaveUp) return;
  let timer = null;
  const timeout = new Promise((resolve) => {
    timer = window.setTimeout(() => {
      fontWaitGaveUp = true;
      resolve();
    }, FONT_FIRST_RENDER_WAIT_MS);
  });
  try {
    await Promise.race([fontTask, timeout]);
  } finally {
    window.clearTimeout(timer);
  }
};

// ---- 描画 ----
const executeRender = async (generation) => {
  const stale = () => generation !== latestGeneration || !dataReady;
  try {
    await waitForFont(); // 最初の描画だけがここで待つ（取得済みなら即通過）
    if (stale()) return;
    await nextPaint(); // 「描画中…」を先に描かせる（Python の実行は同期でメインスレッドを塞ぐ）
    if (stale()) return;
    const result = callPython("render", toJson(), customCodeProvider());
    if (stale()) return;
    if (result.ok) {
      showPlot(result.image, generation);
      const skipped = Number.isInteger(result.skipRows) ? result.skipRows : 0;
      setStatus(`描画に成功しました（${result.seriesCount}系列、スキップ${skipped}行）。`, "ok", "", [
        ...loadWarnings,
        ...warningTexts(result.warnings),
      ]);
    } else {
      reportError(result.error);
    }
  } catch (err) {
    if (generation === latestGeneration) reportException(err, "render");
  }
};

const runRenderLoop = async () => {
  renderRunning = true;
  setRenderState("rendering");
  try {
    do {
      renderDirty = false;
      await executeRender(latestGeneration);
    } while (renderDirty);
  } finally {
    renderRunning = false;
    setRenderState(renderTimer ? "pending" : "idle");
  }
};

// 描画を要求する。実行中なら「やり直し」の印だけ付け、最新の設定で終了後に1回だけ走る。
const requestRender = () => {
  if (!api || !dataReady) return;
  latestGeneration += 1;
  root.dataset.renderGeneration = String(latestGeneration);
  if (renderRunning) {
    renderDirty = true;
    return;
  }
  runRenderLoop();
};

export const scheduleRender = (delay = RENDER_DELAY_MS) => {
  if (renderTimer) window.clearTimeout(renderTimer);
  if (!renderRunning) setRenderState("pending");
  renderTimer = window.setTimeout(() => {
    renderTimer = null;
    if (api && dataReady) requestRender();
    else if (!renderRunning) setRenderState("idle");
  }, delay);
};

export const renderNow = () => {
  if (api && dataReady) {
    if (renderTimer) {
      window.clearTimeout(renderTimer);
      renderTimer = null;
    }
    requestRender();
  }
};

// ---- 読込 ----
const doLoad = async () => {
  if (!api || !selectedFile) return;
  const seq = ++loadSeq;
  const file = selectedFile;
  setDataState("loading");
  if (renderRunning) {
    // 実行中の描画は古いデータのものなので結果を捨てる
    latestGeneration += 1;
    root.dataset.renderGeneration = String(latestGeneration);
  }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (seq !== loadSeq) return;
    if (!excelReady && /\.xlsx$/i.test(file.name)) {
      excelInstalling = true;
      setStatus(EXCEL_LOADING_MESSAGE);
      refreshProgress();
      let installed;
      try {
        installed = JSON.parse(await api.ensureExcel());
      } finally {
        excelInstalling = false;
        refreshProgress();
      }
      if (seq !== loadSeq) return;
      if (!installed.ok) {
        setDataState("error");
        loadWarnings = [];
        showEncoding(undefined);
        reportError(installed.error);
        return;
      }
      excelReady = true;
      setStatus("");
    }
    const loadJson = JSON.stringify({ version: getSettings().version, load: getSettings().load });
    const result = callPython("loadFile", file.name, bytes, loadJson);
    if (seq !== loadSeq) return;
    if (!result.ok) {
      setDataState("error");
      loadWarnings = [];
      showEncoding(undefined);
      reportError(result.error);
      return;
    }
    loadWarnings = warningTexts(result.warnings);
    showEncoding(result.encoding === undefined ? null : result.encoding);
    setColumns(result.columns);
    showPreview(result.preview, getSettings().plot.skipRows);
    setDataState("ready");
    loadCount += 1;
    root.dataset.loadCount = String(loadCount);
    setStatus("");
    renderNow();
  } catch (err) {
    if (seq === loadSeq) {
      setDataState("error");
      reportException(err, "loadFile");
    }
  }
};

export const scheduleLoad = (delay = LOAD_DELAY_MS.file) => {
  if (!selectedFile) return;
  setDataState("loading"); // 読込が済むまで自動再描画は止める
  if (loadTimer) window.clearTimeout(loadTimer);
  if (!api) return; // Python の起動後に handlePythonReady が読み込む
  loadTimer = window.setTimeout(() => {
    loadTimer = null;
    doLoad();
  }, delay);
};

// 同じファイルをもう一度選んだ場合も再読込する（入力欄は main.js が空に戻す）
export const selectFile = (file) => {
  if (!file) return;
  selectedFile = file;
  loadWarnings = [];
  showFileName(file.name);
  scheduleLoad(LOAD_DELAY_MS.file);
};

const downloadDataUri = (filename, dataUri) => {
  if (!filename || !dataUri) return;
  const link = document.createElement("a");
  link.href = dataUri;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
};

export const saveNow = async () => {
  if (!api) return;
  try {
    await waitForFont();
    const result = callPython("save", toJson(), customCodeProvider());
    if (!result.ok) {
      reportError(result.error);
      return;
    }
    downloadDataUri(result.filename, result.dataUri);
    setStatus(`描画データを保存しました: ${result.filename}`, "ok", "", loadWarnings);
  } catch (err) {
    reportException(err, "save");
  }
};

export const getDefaultCustomCode = () => (api ? api.defaultCustomCode() : "");
export const onPythonReady = (fn) => {
  if (api) fn();
  else readyCallbacks.push(fn);
};

const handlePythonReady = () => {
  if (api || !window.mplgui) return;
  api = window.mplgui;
  root.dataset.appState = "ready";
  startFont(); // 起動時のダウンロードと競合しないよう、Python の準備後に始める
  const callbacks = readyCallbacks;
  readyCallbacks = [];
  for (const fn of callbacks) fn();
  refreshProgress();
  scheduleLoad(LOAD_DELAY_MS.file); // 起動前に選ばれたファイルがあれば、最新の設定で読み込んで1回描画する
};

// 設定の変更を、読込・再描画・表示更新・無視のどれにするか振り分ける
const routeChange = (_settings, change) => {
  if (change.origin !== "user") return;
  const path = change.kind === "path" ? change.path : "series";
  if (path === "plot.skipRows") applySkipRows(getSettings().plot.skipRows); // 表の灰色表示は Python を呼ばず即時更新
  if (path.startsWith("load.")) {
    scheduleLoad(path === "load.delimiter" ? LOAD_DELAY_MS.delimiter : LOAD_DELAY_MS.header);
  } else if (!path.startsWith("save.")) {
    scheduleRender();
  }
};

export const initBridge = () => {
  root.dataset.appState = root.dataset.appState || "starting";
  setDataState("none");
  setRenderState("idle");
  setFontState("idle");
  root.dataset.loadCount = "0";
  refreshProgress();
  subscribe(routeChange);
  // フォントが Cache Storage にあれば、Python の起動を待たずに読み出しだけ始める（ダウンロードは起こらない）
  isFontCached().then((cached) => {
    if (cached) startFont();
  });
  if (window.mplgui) handlePythonReady();
  else window.addEventListener("mplgui-ready", handlePythonReady, { once: true });
};
