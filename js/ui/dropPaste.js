// ファイルのドラッグ&ドロップ（ページ全体）と、表の貼り付け（#pasteArea とページ上の paste）。
// どちらも bridge.js の selectFile に渡すだけ（ファイルを選んだのと同じ経路で読み込む）。
// 貼り付けたデータは UTF-8 の pasted_data.tsv というファイルにして読み込む。
import { getSelectedSource, selectFile } from "../bridge.js";
import { setStatus } from "./notify.js";

export const PASTED_FILENAME = "pasted_data.tsv";
export const NOT_A_TABLE_MESSAGE = "貼り付けた内容が表ではありません。Excel などで表の範囲をコピーしてから貼り付けてください。";
const NO_FILE_MESSAGE = "ドロップされたものから読み込めるファイルが見つかりませんでした（フォルダは読み込めません）。";

const hasFiles = (event) => {
  const types = event.dataTransfer && event.dataTransfer.types;
  return !!types && Array.from(types).includes("Files");
};

// ---- ドロップ ----
// D6 では、データが読込済みのときにここへ「置き換える」「追加する」の2区画（#dropReplace / #dropAdd）を出す。
const overlay = () => document.getElementById("dropOverlay");
let dragDepth = 0;

const showOverlay = () => {
  const el = overlay();
  if (!el) return;
  el.hidden = false;
  el.setAttribute("aria-hidden", "false");
};
const hideOverlay = () => {
  dragDepth = 0;
  const el = overlay();
  if (!el) return;
  el.hidden = true;
  el.setAttribute("aria-hidden", "true");
};

// ドロップされた項目からファイルだけを取り出す（フォルダは除く。drop イベントの中で同期的に呼ぶ）
const droppedFiles = (dataTransfer) => {
  const files = [];
  const items = dataTransfer.items ? Array.from(dataTransfer.items) : [];
  if (items.length > 0) {
    for (const item of items) {
      if (item.kind !== "file") continue;
      const entry = typeof item.webkitGetAsEntry === "function" ? item.webkitGetAsEntry() : null;
      if (entry && entry.isDirectory) continue;
      const file = item.getAsFile();
      if (file) files.push(file);
    }
    return files;
  }
  return Array.from(dataTransfer.files || []);
};

const handleDrop = (event) => {
  const files = droppedFiles(event.dataTransfer);
  if (files.length === 0) {
    setStatus(NO_FILE_MESSAGE, "warning");
    return;
  }
  const notes = files.length > 1 ? [`複数のファイルがドロップされました。先頭の「${files[0].name}」だけを読み込みました。`] : [];
  selectFile(files[0], { notes });
};

const bindDrop = () => {
  window.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    showOverlay();
  });
  window.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault(); // ブラウザがファイルを開かないように
    event.dataTransfer.dropEffect = "copy";
    showOverlay();
  });
  window.addEventListener("dragleave", (event) => {
    if (!hasFiles(event)) return;
    dragDepth -= 1;
    if (dragDepth <= 0) hideOverlay();
  });
  window.addEventListener("drop", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    hideOverlay();
    handleDrop(event);
  });
  window.addEventListener("dragend", hideOverlay);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideOverlay();
  });
};

// ---- 貼り付け ----
const isTable = (text) => text.includes("\t") || text.split("\n").filter((line) => line.trim() !== "").length >= 2;

const loadPastedText = (rawText) => {
  const text = String(rawText || "").replace(/\r\n?/g, "\n");
  if (!isTable(text)) {
    setStatus(NOT_A_TABLE_MESSAGE, "warning");
    return;
  }
  selectFile(new File([text], PASTED_FILENAME, { type: "text/tab-separated-values" }), { pasted: true });
};

const isEditable = (el) => !!el && el instanceof Element && el.closest("input, textarea, select, [contenteditable]") !== null;

const bindPaste = () => {
  const area = document.getElementById("pasteArea");
  if (area) {
    area.addEventListener("paste", (event) => {
      event.preventDefault();
      const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
      area.value = "";
      loadPastedText(text);
    });
    // メニューの「貼り付け」などで、paste を経ずに値が入った場合
    area.addEventListener("input", () => {
      const text = area.value;
      area.value = "";
      if (text !== "") loadPastedText(text);
    });
  }
  document.addEventListener("paste", (event) => {
    if (isEditable(event.target) || isEditable(document.activeElement)) return; // 入力欄への貼り付けは通常どおり
    const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (text.trim() === "") return;
    event.preventDefault();
    loadPastedText(text);
  });
};

// ---- 貼り付けたデータの保存 ----
const bindSavePasted = () => {
  const button = document.getElementById("savePastedBtn");
  if (!button) return;
  button.addEventListener("click", async () => {
    const { file, pasted } = getSelectedSource();
    if (!file || !pasted) return;
    const blob = new Blob([await file.arrayBuffer()], { type: "text/tab-separated-values" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = PASTED_FILENAME;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
};

export const bindDropPaste = () => {
  bindDrop();
  bindPaste();
  bindSavePasted();
};
