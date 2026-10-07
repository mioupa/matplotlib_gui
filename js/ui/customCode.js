// Pythonコード(beta)タブ。コード本文と「使用する」は設定オブジェクトには入れず、描画要求のたびに別引数で渡す。
import { canAutoRender, renderNow, scheduleRender, setCustomCodeProvider } from "../bridge.js";

const customCodeInput = () => document.getElementById("customPyCode");
const useCustomCodeInput = () => document.getElementById("useCustomCode");

// 有効時はコード文字列、無効時は null
export const getCustomCode = () => {
  const use = useCustomCodeInput();
  const editor = customCodeInput();
  return use && use.checked && editor ? String(editor.value || "") : null;
};

// Python 起動後に既定コードを入れる（未入力のときだけ）
export const initDefaultCode = (defaultCode) => {
  const editor = customCodeInput();
  if (!editor) return;
  editor.dataset.defaultCode = defaultCode;
  if (!String(editor.value || "").trim()) editor.value = defaultCode;
};

export const bindCustomCodeEvents = () => {
  setCustomCodeProvider(getCustomCode);
  const use = useCustomCodeInput();
  const editor = customCodeInput();
  const applyBtn = document.getElementById("applyCustomCodeBtn");
  const resetBtn = document.getElementById("resetCustomCodeBtn");

  if (use) use.addEventListener("change", () => scheduleRender(0));
  if (applyBtn) applyBtn.addEventListener("click", () => renderNow());
  if (resetBtn && editor) {
    resetBtn.addEventListener("click", () => {
      editor.value = editor.dataset.defaultCode || "";
      if (use) use.checked = false;
      if (canAutoRender()) renderNow();
    });
  }
  if (editor) {
    editor.addEventListener("keydown", (event) => {
      if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
      event.preventDefault();
      renderNow();
    });
  }
};
