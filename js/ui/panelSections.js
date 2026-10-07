// 設定パネルの折りたたみ状態。利用者ごとの便宜なので localStorage にだけ持つ（設定オブジェクトには入れない）。
// localStorage が使えない・例外を投げる環境では、すべて開いた状態で動く。
const STORAGE_KEY = "mplgui.panelSections";

const readStored = () => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const value = JSON.parse(raw);
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch (_) {
    return {};
  }
};

const writeStored = (value) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch (_) {
    // 保存できなくても動作には影響しない
  }
};

export const initPanelSections = () => {
  const sections = Array.from(document.querySelectorAll("details.panel-section"));
  const stored = readStored();
  for (const el of sections) {
    if (typeof stored[el.id] === "boolean") el.open = stored[el.id];
  }
  for (const el of sections) {
    el.addEventListener("toggle", () => {
      const state = readStored();
      state[el.id] = el.open;
      writeStored(state);
    });
  }
};
