// Pythonコードタブ。モード（code-state.js）に応じて、textarea・ボタン・同期表示を切り替える。
//   sync: 読み取り専用。GUI から生成したスクリプトを表示（描画の成功ごとに更新）。
//   edit: 編集可。GUI の変更では上書きしない。「実行」（Ctrl/Cmd+Enter）でそのコードを実行する。
import { enterEditMode, isDataReady, leaveEditMode, runCode, scriptFilename, setEditCodeProvider } from "../bridge.js";
import { getCodeMode, getGeneratedCode, getGeneratedGeneration, isEditMode, subscribeCode } from "../code-state.js";
import { setStatus } from "./notify.js";

const $ = (id) => document.getElementById(id);

const SYNC_TEXT = "GUI と同期しています";
const EDIT_TEXT = "GUI と同期していません";

// 行番号の列。textarea と同じ行数だけ 1 から並べる（トレースバックの「line N」と対応させる）
const updateGutter = () => {
  const editor = $("customPyCode");
  const gutter = $("codeLineNumbers");
  if (!editor || !gutter) return;
  const count = Math.max(1, editor.value.split("\n").length);
  const text = Array.from({ length: count }, (_, i) => String(i + 1)).join("\n");
  if (gutter.textContent !== text) gutter.textContent = text;
  gutter.scrollTop = editor.scrollTop;
};

const showGenerated = () => {
  const editor = $("customPyCode");
  if (!editor) return;
  editor.value = getGeneratedCode();
  const generation = getGeneratedGeneration();
  if (generation === null) delete editor.dataset.generation;
  else editor.dataset.generation = String(generation);
  updateGutter();
};

const applyMode = () => {
  const edit = isEditMode();
  const editor = $("customPyCode");
  if (editor) {
    editor.readOnly = !edit;
    editor.setAttribute("aria-readonly", edit ? "false" : "true");
  }
  const wrap = document.querySelector(".code-editor-wrap");
  if (wrap) wrap.classList.toggle("is-edit", edit);
  const badge = $("codeSyncStatus");
  if (badge) {
    badge.textContent = edit ? EDIT_TEXT : SYNC_TEXT;
    badge.dataset.state = edit ? "edit" : "sync";
  }
  // 現在のモードに当てはまるボタンだけを出す（コピー・.py で保存は常に）
  const visible = {
    editCodeBtn: !edit,
    applyCustomCodeBtn: edit,
    resetCustomCodeBtn: edit,
    copyCodeBtn: true,
    downloadCodeBtn: true,
  };
  for (const [id, show] of Object.entries(visible)) {
    const btn = $(id);
    if (btn) btn.hidden = !show;
  }
};

const copyWithSelection = (editor) => {
  const keepStart = editor.selectionStart;
  const keepEnd = editor.selectionEnd;
  editor.focus();
  editor.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (_) {
    ok = false;
  }
  editor.setSelectionRange(keepStart, keepEnd);
  return ok;
};

const copyCode = async () => {
  const editor = $("customPyCode");
  if (!editor) return;
  const text = editor.value;
  if (!text.trim()) {
    setStatus("コピーするコードがありません。ファイルを読み込んでください。", "warning");
    return;
  }
  let ok = false;
  try {
    await navigator.clipboard.writeText(text);
    ok = true;
  } catch (_) {
    ok = copyWithSelection(editor);
  }
  if (ok) setStatus("Pythonコードをコピーしました。", "ok");
  else setStatus("コピーできませんでした。コードを選択して、手動でコピーしてください。", "error");
};

const downloadCode = () => {
  const editor = $("customPyCode");
  if (!editor) return;
  const text = editor.value;
  if (!text.trim()) {
    setStatus("保存するコードがありません。ファイルを読み込んでください。", "warning");
    return;
  }
  try {
    const name = scriptFilename();
    const url = URL.createObjectURL(new Blob([text], { type: "text/x-python;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    setStatus(`Pythonコードを保存しました: ${name}`, "ok");
  } catch (_) {
    setStatus("Pythonコードを保存できませんでした。", "error");
  }
};

export const bindCodeTab = () => {
  const editor = $("customPyCode");
  setEditCodeProvider(() => (editor ? editor.value : ""));

  subscribeCode((_state, change) => {
    if (change.kind === "mode") {
      applyMode();
      if (!isEditMode()) showGenerated(); // 「GUI から再生成」: 直近の生成コードをすぐ表示する
    } else if (getCodeMode() === "sync") {
      showGenerated(); // 編集中は GUI 由来のコードで上書きしない
    }
  });

  $("editCodeBtn")?.addEventListener("click", () => {
    enterEditMode();
    if (editor) editor.focus();
  });
  $("applyCustomCodeBtn")?.addEventListener("click", () => runCode());
  $("resetCustomCodeBtn")?.addEventListener("click", () => leaveEditMode());
  $("copyCodeBtn")?.addEventListener("click", () => copyCode());
  $("downloadCodeBtn")?.addEventListener("click", () => downloadCode());

  if (editor) {
    editor.addEventListener("keydown", (event) => {
      if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
      event.preventDefault();
      if (isEditMode() || isDataReady()) runCode();
    });
    editor.addEventListener("input", updateGutter);
    editor.addEventListener("scroll", () => {
      const gutter = $("codeLineNumbers");
      if (gutter) gutter.scrollTop = editor.scrollTop;
    });
  }
  applyMode();
  updateGutter();
};
