// Pythonコード(beta)タブ。コード本文と「使用する」は設定オブジェクトには入れず、描画要求のたびに別引数で渡す。
import { canAutoRender, onGeneratedCode, renderNow, scheduleRender, setCustomCodeProvider } from "../bridge.js";

const customCodeInput = () => document.getElementById("customPyCode");
const useCustomCodeInput = () => document.getElementById("useCustomCode");

// 有効時はコード文字列、無効時は null
export const getCustomCode = () => {
  const use = useCustomCodeInput();
  const editor = customCodeInput();
  return use && use.checked && editor ? String(editor.value || "") : null;
};

// GUI 設定から生成したスクリプトを表示する。「使用する」が無効のときだけ上書きする（編集中のコードは守る）
export const showGeneratedCode = (code) => {
  const editor = customCodeInput();
  if (!editor) return;
  editor.dataset.defaultCode = code;
  const use = useCustomCodeInput();
  if (!use || !use.checked) editor.value = code;
};

export const bindCustomCodeEvents = () => {
  setCustomCodeProvider(getCustomCode);
  onGeneratedCode(showGeneratedCode);
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
