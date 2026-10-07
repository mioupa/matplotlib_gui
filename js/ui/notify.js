// ステータス表示と、parentNode 系例外の抑制・回復ハンドラ。
// 他のモジュールより先に評価されるよう、main.js の先頭で import する。
const __warn = console.warn.bind(console);
const isTargetError = (msg) =>
  typeof msg === "string" &&
  (msg.includes("parentNode") || msg.includes("'NoneType' object has no attribute 'parentNode'"));

const logSuppressed = (where, msg, stack = "") => {
  try {
    __warn("[mplgui] suppressed parentNode error:", where, String(msg));
  } catch (_) {}
};

const buildJsErrorDetail = (source, msg, stack = "", extras = []) => {
  const lines = [`source: ${source}`];
  if (msg) lines.push(`message: ${msg}`);
  for (const extra of extras) {
    if (extra) lines.push(extra);
  }
  const normalizedStack = typeof stack === "string" ? stack.trim() : "";
  if (normalizedStack) {
    lines.push("");
    lines.push("stack:");
    lines.push(normalizedStack);
  }
  return lines.join("\n");
};

export const setStatus = (message, isError = false, detail = "") => {
  const status = document.getElementById("status");
  if (status) {
    status.textContent = message || "";
    status.style.color = isError ? "var(--status-error)" : "var(--status-ok)";
  }

  const detailWrap = document.getElementById("statusDetailWrap");
  const detailEl = document.getElementById("statusDetail");
  if (!detailWrap || !detailEl) return;
  const normalized = typeof detail === "string" ? detail.trim() : "";
  if (normalized) {
    detailEl.textContent = normalized;
    detailWrap.classList.remove("hidden");
    detailWrap.open = true;
  } else {
    detailEl.textContent = "";
    detailWrap.classList.add("hidden");
    detailWrap.open = false;
  }
};

export const notify = (detail = "") => {
  const plotArea = document.getElementById("plotArea");
  const hasPlot = !!(plotArea && plotArea.querySelector("img"));
  if (hasPlot) {
    setStatus("描画に成功しました。");
  } else {
    setStatus("内部エラーを自動回避しました。もう一度操作してください。", true, detail);
  }
};

window.addEventListener("error", (event) => {
  const msg = event?.message || "";
  if (isTargetError(msg)) {
    event.preventDefault();
    const stack = event?.error?.stack || "";
    logSuppressed("window.error", msg, stack);
    const extras = [
      event?.filename ? `file: ${event.filename}` : "",
      event?.lineno ? `line: ${event.lineno}` : "",
      event?.colno ? `column: ${event.colno}` : "",
    ];
    notify(buildJsErrorDetail("window.error", msg, stack, extras));
  }
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event?.reason;
  const msg = (reason && (reason.message || String(reason))) || "";
  if (isTargetError(msg)) {
    event.preventDefault();
    const stack = reason?.stack || "";
    logSuppressed("window.unhandledrejection", msg, stack);
    notify(buildJsErrorDetail("window.unhandledrejection", msg, stack));
  }
});

const originalConsoleError = console.error.bind(console);
console.error = (...args) => {
  const msg = args.map((x) => String(x)).join(" ");
  if (isTargetError(msg)) {
    logSuppressed("console.error", msg, new Error().stack || "");
    notify(buildJsErrorDetail("console.error", msg));
    return;
  }
  originalConsoleError(...args);
};
