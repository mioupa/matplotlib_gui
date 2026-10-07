// Python（window.mplgui）との唯一の窓口。設定は JSON 文字列で渡し、結果の JSON を UI へ反映する。
// - 再描画は設定変更の 250ms 後（デバウンス）、読込はファイル/ヘッダ 0ms・区切り文字 450ms。保存設定の変更では再描画しない。
// - 描画要求には世代番号を振る。同時に走る Python 描画は最大1つで、実行中の要求は「やり直し」の印だけ付け、
//   終わったあと最新の設定で1回だけ描画する。古い世代の結果は画像・ステータスに反映しない。
// - Python の起動前に選んだファイル・変えた設定は保持され、起動後に最新の内容で1回読込・描画する。
// - Pythonコードタブのモード（code-state.js）: sync は GUI の設定から生成したコードで描く。edit は利用者が編集したコードを
//   「実行」したときだけ描き、GUI の変更では再描画しない（読込は行うが自動実行しない）。
import { subscribe, toJson, getSettings } from "./state.js";
import { addStickyWarning, removeStickyWarning, setStatus, warningTexts } from "./ui/notify.js";
import { showPlot } from "./ui/plotView.js";
import { showCodeOutput } from "./ui/codeOutput.js";
import { getGeneratedGeneration, isEditMode, setCodeMode, setGeneratedCode } from "./code-state.js";
import { applySkipRows, showPreview } from "./ui/dataPreview.js";
import { setColumns } from "./ui/series.js";
import { showEncoding, showFileName } from "./ui/fileInfo.js";
import { setBusy, showProgress } from "./ui/progress.js";
import { RUNTIME_MESSAGE, watchStartup } from "./startup-progress.js";
import { FONT_FIRST_RENDER_WAIT_MS, isFontCached, loadFont } from "./font-cache.js";

const RENDER_DELAY_MS = 250;
const LOAD_DELAY_MS = { file: 0, header: 0, delimiter: 450 };
const FONT_FAILED_MESSAGE = "日本語フォントを取得できませんでした。日本語が正しく表示されない場合があります。";
const FONT_LOADING_MESSAGE = "日本語フォントを取得中…";
const LATIN_LOADING_MESSAGE = "欧文フォントを取得中…";
const LATIN_NAMES = { arimo: "Arimo", tinos: "Tinos" };
const latinFailedMessage = (kind) => `欧文フォント ${LATIN_NAMES[kind]} を取得できなかったため、標準のフォントで描画しています。`;
const SCRIPT_REFRESH_DELAY_MS = 250;

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
let editCodeProvider = () => ""; // 編集モードのコード（Pythonコードタブの textarea の内容）
let editHasRun = false; // 編集モードに入ってから「実行」したことがある（フォント取得後の描き直しの判断に使う）
let readyCallbacks = [];
let fontState = "idle"; // idle | loading | ready | failed
let fontPercent = null;
let fontTask = null;
let excelInstalling = false; // 初回の .xlsx 読込前に Excel 用ライブラリを取得中
let excelReady = false;
let startupMessage = RUNTIME_MESSAGE; // Python 起動中の段階表示（startup-progress.js）
let stopStartupWatch = () => {};
let fontWaitGaveUp = false; // 最初の描画がフォント待ちを打ち切った（以後は待たない）
const latinTasks = new Map(); // 欧文フォントの種類 → {state: loading|ready|failed, promise, gaveUp}。取得は種類ごとにセッション中1回
let scriptTimer = null; // 保存設定の変更に伴う、コードだけの更新（画像は変えない）
let scriptRefreshAfterRender = false;
let scriptRefreshFailed = false;
let lastRenderStatus = null; // 直近の描画成功のステータス（コード更新のエラーから復帰したときに戻す）

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
export const isDataReady = () => dataReady;
export const setEditCodeProvider = (fn) => {
  editCodeProvider = fn;
};

const EDIT_MODE_MESSAGE =
  "Pythonコードを編集中のため、GUI の変更は図に反映されません。「Pythonコード」タブの「GUI から再生成」で戻せます。";
const PYTHON_NOT_READY_MESSAGE = "Python の起動が終わってから実行してください。";

// 描画に渡すコード: GUI 同期なら null（設定から生成）、編集モードなら textarea の内容
const currentCode = () => (isEditMode() ? String(editCodeProvider() || "") : null);
// sync は読込済みデータが必要。edit は Python が動いていればよい（コードが自分でファイルを読む）
const canRender = () => api !== null && (isEditMode() || dataReady);

const EXCEL_LOADING_MESSAGE = "Excel 読込用のライブラリを取得中…";

const callPython = (name, ...args) => JSON.parse(api[name](...args));

const reportError = (error) => {
  setStatus(error.message, "error", error.detail || error.traceback || "");
};
const reportException = (err, context) => {
  const detail = `context: ${context}\n${err && err.stack ? err.stack : String(err)}`;
  setStatus("内部エラーが発生しました。もう一度操作してください。", "error", detail);
};

// 進捗バナー: Python 起動中はその旨、起動後はフォント取得の進捗、どちらも無ければ非表示
const refreshProgress = () => {
  if (!api) showProgress(startupMessage);
  else if (excelInstalling) showProgress(EXCEL_LOADING_MESSAGE);
  else if (fontState === "loading") showProgress(fontPercent === null ? FONT_LOADING_MESSAGE : `${FONT_LOADING_MESSAGE} ${fontPercent}%`);
  else if (root.dataset.latinFontState === "loading") showProgress(LATIN_LOADING_MESSAGE);
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
    const bytes = await loadFont("japanese", (p) => {
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
        if (fontWaitGaveUp && (!isEditMode() || editHasRun)) renderNow(); // フォント無しで描いた図を、現在の設定で1回だけ描き直す（通常の合流処理・新しい世代）
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

// ---- 欧文フォント（C3）。選んだときだけ取得する（起動時には取得しない）。失敗は警告を出し、標準のフォントで続行する ----
const selectedLatin = () => getSettings().plot.latinFont;

// data-latin-font-state（選択中の欧文フォントの状態）と、選択中のフォントの取得失敗の警告を、現在の選択に合わせる
const refreshLatinState = () => {
  const kind = selectedLatin();
  const task = latinTasks.get(kind);
  root.dataset.latinFontState = kind === "default" ? "idle" : task ? task.state : "loading";
  for (const [other, t] of latinTasks) {
    if (t.state === "failed" && other === kind) addStickyWarning(latinFailedMessage(other));
    else removeStickyWarning(latinFailedMessage(other));
  }
};

const startLatinFont = (kind) => {
  if (!api || !LATIN_NAMES[kind]) return null;
  const existing = latinTasks.get(kind);
  if (existing) return existing;
  const task = { state: "loading", promise: null, gaveUp: false };
  latinTasks.set(kind, task);
  task.promise = (async () => {
    const bytes = await loadFont(kind);
    let registered = false;
    if (bytes) {
      try {
        registered = JSON.parse(api.registerFont(bytes, kind)).ok === true;
      } catch (_) {
        registered = false;
      }
    }
    task.state = registered ? "ready" : "failed";
    refreshLatinState();
    refreshProgress();
    // 待ちを打ち切ってフォールバックで描いた図を、現在の設定で1回だけ描き直す
    if (registered && task.gaveUp && selectedLatin() === kind && (!isEditMode() || editHasRun)) renderNow();
  })();
  refreshLatinState();
  refreshProgress();
  return task;
};

// 描画（と保存）は、取得中のフォントを最大 FONT_FIRST_RENDER_WAIT_MS だけ待つ。超えたらフォールバックフォントで描き、
// 取得完了後に1回だけ再描画する（日本語は最初の描画だけ待つ。欧文は選んだフォントごとに1回だけ待つ）。
const waitForFonts = async () => {
  const pending = [];
  const latin = latinTasks.get(selectedLatin());
  const waitJapanese = fontState === "loading" && fontTask && !fontWaitGaveUp;
  const waitLatin = latin && latin.state === "loading" && !latin.gaveUp;
  if (waitJapanese) pending.push(fontTask);
  if (waitLatin) pending.push(latin.promise);
  if (pending.length === 0) return;
  let timer = null;
  const timeout = new Promise((resolve) => {
    timer = window.setTimeout(() => {
      if (waitJapanese && fontState === "loading") fontWaitGaveUp = true;
      if (waitLatin && latin.state === "loading") latin.gaveUp = true;
      resolve();
    }, FONT_FIRST_RENDER_WAIT_MS);
  });
  try {
    await Promise.race([Promise.all(pending), timeout]);
  } finally {
    window.clearTimeout(timer);
  }
};

// ---- 描画 ----
const executeRender = async (generation) => {
  const stale = () => generation !== latestGeneration || !canRender();
  try {
    await waitForFonts(); // 取得中のフォントがあれば、ここで最大 FONT_FIRST_RENDER_WAIT_MS 待つ（取得済みなら即通過）
    if (stale()) return;
    await nextPaint(); // 「描画中…」を先に描かせる（Python の実行は同期でメインスレッドを塞ぐ）
    if (stale()) return;
    const editing = isEditMode();
    const result = callPython("render", toJson(), currentCode());
    if (stale()) return;
    if (result.ok) {
      showPlot(result.image, generation, result.summary);
      showCodeOutput({ output: result.output, kind: "ok" });
      if (!editing && typeof result.code === "string" && !isEditMode()) setGeneratedCode(result.code, generation);
      if (Number.isInteger(result.seriesCount)) {
        const skipped = Number.isInteger(result.skipRows) ? result.skipRows : 0;
        const warnings = [...loadWarnings, ...warningTexts(result.warnings)];
        lastRenderStatus = { message: `描画に成功しました（${result.seriesCount}系列、スキップ${skipped}行）。`, detail: "", warnings };
      } else {
        lastRenderStatus = { message: "コードの実行に成功しました。", detail: result.output || "", warnings: loadWarnings };
      }
      scriptRefreshFailed = false;
      setStatus(lastRenderStatus.message, "ok", lastRenderStatus.detail, lastRenderStatus.warnings);
    } else {
      const traceback = result.error && result.error.traceback ? result.error.traceback : "";
      showCodeOutput({ output: result.output, traceback, kind: traceback ? "error" : "ok" });
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
    if (scriptRefreshAfterRender) {
      scriptRefreshAfterRender = false;
      scheduleScriptRefresh();
    }
  }
};

// 描画を要求する。実行中なら「やり直し」の印だけ付け、最新の設定で終了後に1回だけ走る。
const requestRender = () => {
  if (!canRender()) return;
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
    if (canRender()) requestRender();
    else if (!renderRunning) setRenderState("idle");
  }, delay);
};

export const renderNow = () => {
  if (canRender()) {
    if (renderTimer) {
      window.clearTimeout(renderTimer);
      renderTimer = null;
    }
    requestRender();
  }
};

// ---- 保存設定の変更に伴うコードの更新（GUI 同期のみ。画像は描き直さない）----
// 画像の画素は保存設定に依存しないので、表示中のコード（世代は画像のまま）の savefig 行・rcParams だけを生成し直す。
// 描画が予約中・実行中のときは、描画が新しいコードを返すので何もしない（実行中だった場合は終了後にもう一度確かめる）。
const refreshScript = () => {
  scriptTimer = null;
  if (!api || !dataReady || isEditMode() || getGeneratedGeneration() === null) return;
  if (renderTimer !== null) return;
  if (renderRunning) {
    scriptRefreshAfterRender = true;
    return;
  }
  try {
    const result = callPython("script", toJson());
    if (isEditMode()) return;
    if (result.ok) {
      setGeneratedCode(result.code, getGeneratedGeneration());
      if (scriptRefreshFailed) {
        scriptRefreshFailed = false;
        const last = lastRenderStatus;
        if (last) setStatus(last.message, "ok", last.detail, last.warnings);
        else setStatus("");
      }
    } else {
      scriptRefreshFailed = true;
      reportError(result.error);
    }
  } catch (err) {
    reportException(err, "script");
  }
};

const scheduleScriptRefresh = () => {
  if (scriptTimer) window.clearTimeout(scriptTimer);
  scriptTimer = window.setTimeout(refreshScript, SCRIPT_REFRESH_DELAY_MS);
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
    if (isEditMode()) {
      setStatus(EDIT_MODE_MESSAGE, "warning"); // 編集中は自動で実行しない（ファイルは作業フォルダに置かれている）
    } else {
      setStatus("");
      renderNow();
    }
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

// ---- Pythonコードタブのモード切替・実行 ----
// 予約済み・実行中の GUI 同期描画を無効にする（世代を進める。結果は画像にもコードにもステータスにも反映されない）
const invalidatePendingRender = () => {
  const pending = renderTimer !== null;
  if (renderTimer) {
    window.clearTimeout(renderTimer);
    renderTimer = null;
  }
  if (pending || renderRunning) {
    latestGeneration += 1;
    root.dataset.renderGeneration = String(latestGeneration);
  }
  renderDirty = false;
  setRenderState(renderRunning ? "rendering" : "idle");
};

export const enterEditMode = () => {
  if (isEditMode()) return;
  invalidatePendingRender();
  editHasRun = false;
  setCodeMode("edit");
};

// 「GUI から再生成」: 同期に戻し、現在の設定でコードと図を作り直す（データが無ければモードだけ戻す）
export const leaveEditMode = () => {
  if (!isEditMode()) return;
  invalidatePendingRender();
  setCodeMode("sync");
  setStatus("");
  if (api && dataReady) requestRender(); // 実行中の編集コードの結果は、世代が進むので捨てられる
};

// 編集モードのコードを実行する（同期モードでは GUI の設定で再描画する）
export const runCode = () => {
  if (!api) {
    setStatus(PYTHON_NOT_READY_MESSAGE, "warning");
    return;
  }
  if (isEditMode()) editHasRun = true;
  renderNow();
};

// 「.py で保存」のファイル名。Python の formats.build_filename と同じ規則（Python が使えないときだけ既定名）
export const scriptFilename = () => {
  if (!api || typeof api.scriptFilename !== "function") return "plot.py";
  return String(api.scriptFilename(getSettings().save.filename));
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
    await waitForFonts();
    const result = callPython("save", toJson(), currentCode());
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

// クリップボードにコピーする PNG を作る（保存と同じ設定: GUI 同期は現在の設定、編集モードは編集中のコード）。
// js/ui/clipboard.js がクリックの中で ClipboardItem に渡す Promise になる。失敗は保存と同じ表示にして、reported = true で投げ直す。
const reportedError = (message, original) => {
  const error = new Error(message);
  error.reported = true;
  error.cause = original;
  return error;
};

export const makeClipboardImage = async () => {
  if (!api) {
    setStatus(PYTHON_NOT_READY_MESSAGE, "warning");
    throw reportedError("python not ready");
  }
  try {
    await waitForFonts();
    const result = callPython("copyImage", toJson(), currentCode());
    if (!result.ok) {
      reportError(result.error);
      throw reportedError(result.error.message);
    }
    const binary = atob(result.dataUri.slice(result.dataUri.indexOf(",") + 1));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return { blob: new Blob([bytes], { type: result.mime || "image/png" }), width: result.width, height: result.height };
  } catch (err) {
    if (err && err.reported) throw err;
    reportException(err, "copyImage");
    throw reportedError("internal error", err);
  }
};

export const onPythonReady = (fn) => {
  if (api) fn();
  else readyCallbacks.push(fn);
};

const handlePythonReady = () => {
  if (api || !window.mplgui) return;
  api = window.mplgui;
  stopStartupWatch();
  root.dataset.startupStage = "ready";
  root.dataset.appState = "ready";
  startFont(); // 起動時のダウンロードと競合しないよう、Python の準備後に始める
  startLatinFont(selectedLatin()); // 起動前に欧文フォントを選んでいた場合だけ（既定の「標準」では何もしない）
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
  } else if (path.startsWith("save.")) {
    if (!isEditMode()) scheduleScriptRefresh(); // 画像は変わらない。保存設定を反映したコードだけ作り直す
  } else {
    if (path === "plot.latinFont") {
      startLatinFont(selectedLatin()); // 選んだときだけ取得する（編集モードでも取得・登録する。描画もコードも触らない）
      refreshLatinState();
    }
    if (isEditMode()) setStatus(EDIT_MODE_MESSAGE, "warning"); // 編集中は再描画もコードの更新もしない
    else scheduleRender();
  }
};

export const initBridge = () => {
  root.dataset.appState = root.dataset.appState || "starting";
  setDataState("none");
  setRenderState("idle");
  setFontState("idle");
  refreshLatinState();
  root.dataset.loadCount = "0";
  stopStartupWatch = watchStartup((stage, message) => {
    startupMessage = message;
    root.dataset.startupStage = stage; // runtime | packages | init（Python の準備後は ready）
    if (!api) refreshProgress();
  });
  refreshProgress();
  subscribe(routeChange);
  // フォントが Cache Storage にあれば、Python の起動を待たずに読み出しだけ始める（ダウンロードは起こらない）
  isFontCached("japanese").then((cached) => {
    if (cached) startFont();
  });
  if (window.mplgui) handlePythonReady();
  else window.addEventListener("mplgui-ready", handlePythonReady, { once: true });
};
