// Pythonコード(beta)タブのボタン・ショートカット。
import { canAutoRender, runPyAction, scheduleRender } from "../bridge.js";

const customCodeInput = document.getElementById("customPyCode");
const useCustomCodeInput = document.getElementById("useCustomCode");
const applyCustomCodeBtn = document.getElementById("applyCustomCodeBtn");
const resetCustomCodeBtn = document.getElementById("resetCustomCodeBtn");

export const bindCustomCodeEvents = () => {
  if (useCustomCodeInput) {
    useCustomCodeInput.addEventListener("change", () => scheduleRender(0));
  }
  if (applyCustomCodeBtn) {
    applyCustomCodeBtn.addEventListener("click", () => {
      if (canAutoRender()) {
        runPyAction("requestRender");
      }
    });
  }
  if (resetCustomCodeBtn && customCodeInput) {
    resetCustomCodeBtn.addEventListener("click", () => {
      const defaultCode = customCodeInput.dataset.defaultCode || "";
      customCodeInput.value = defaultCode;
      if (useCustomCodeInput) {
        useCustomCodeInput.checked = false;
      }
      if (canAutoRender()) {
        runPyAction("requestRender");
      }
    });
  }
  if (customCodeInput) {
    customCodeInput.addEventListener("keydown", (event) => {
      if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
      event.preventDefault();
      if (canAutoRender()) {
        runPyAction("requestRender");
      }
    });
  }
};
