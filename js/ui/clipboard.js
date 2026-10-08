// 「クリップボードにコピー」（C5）。保存 DPI の PNG を、ClipboardItem に Promise<Blob> として渡して書き込む。
// Safari はユーザー操作（クリック）の中で write を呼ぶ必要があるので、クリックの処理では何も await せずに write を呼び、
// 画像は渡した Promise の中で作る（Chrome 98 以降、Edge、Safari 13.1 以降、Firefox 127 以降が Promise<Blob> を受け付ける）。
// 状態は <html data-copy-state="idle|copying|done|failed|unsupported">。
import { getSettings } from "../state.js";
import { makeClipboardImage } from "../bridge.js";
import { setStatus } from "./notify.js";

const root = document.documentElement;

const UNSUPPORTED_MESSAGE = "このブラウザでは図をクリップボードにコピーできません。「保存する」で PNG を保存してください。";
const REJECTED_MESSAGE = "クリップボードにコピーできませんでした。ページをクリックしてから、もう一度試してください。";

const setCopyState = (state) => {
  root.dataset.copyState = state;
};

export const isClipboardSupported = () => {
  try {
    return (
      window.isSecureContext === true &&
      !!(navigator.clipboard && navigator.clipboard.write) &&
      typeof ClipboardItem !== "undefined" &&
      (typeof ClipboardItem.supports === "function" ? ClipboardItem.supports("image/png") : true)
    );
  } catch (_) {
    return false;
  }
};

const onCopyClick = () => {
  if (root.dataset.copyState === "copying") return;
  if (!isClipboardSupported()) {
    setCopyState("unsupported");
    setStatus(UNSUPPORTED_MESSAGE, "warning");
    return;
  }
  setCopyState("copying");
  let info = null;
  let pythonFailed = false;
  const pngPromise = makeClipboardImage().then(
    (image) => {
      info = image;
      return image.blob;
    },
    (err) => {
      pythonFailed = true; // 失敗の表示は bridge.js が済ませている（保存と同じ表示）
      throw err;
    },
  );
  let written;
  try {
    written = navigator.clipboard.write([new ClipboardItem({ "image/png": pngPromise })]);
  } catch (err) {
    written = Promise.reject(err);
  }
  written.then(
    () => {
      setCopyState("done");
      const dpi = getSettings().save.dpi;
      setStatus(`図をクリップボードにコピーしました（PNG、${dpi} dpi、${info.width} × ${info.height} ピクセル）。`, "ok");
    },
    () => {
      setCopyState("failed");
      if (!pythonFailed) setStatus(REJECTED_MESSAGE, "error");
    },
  );
};

export const bindClipboard = () => {
  setCopyState("idle");
  const button = document.getElementById("copyPlotBtn");
  if (button) button.addEventListener("click", onCopyClick);
};
