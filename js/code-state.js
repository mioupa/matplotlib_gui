// Pythonコードタブの状態。設定オブジェクト（state.js）には入れない（スキーマは version 1 のまま）。
//   mode: "sync"（GUI から生成したコードを表示。GUI の変更で更新）| "edit"（利用者が編集。GUI の変更では上書きしない）
//   generatedCode: 直近の GUI 同期の描画で得たスクリプト全体（generation はそのときの世代番号）
// DOM には <html data-code-mode="sync|edit"> だけ反映する。
const root = typeof document !== "undefined" ? document.documentElement : null;
const listeners = new Set();
const state = { mode: "sync", generatedCode: "", generation: null };

if (root) root.dataset.codeMode = state.mode;

const notify = (change) => {
  for (const fn of Array.from(listeners)) fn({ ...state }, change);
};

export const getCodeMode = () => state.mode;
export const isEditMode = () => state.mode === "edit";
export const getGeneratedCode = () => state.generatedCode;
export const getGeneratedGeneration = () => state.generation;

export const subscribeCode = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

export const setCodeMode = (mode) => {
  if (mode !== "sync" && mode !== "edit") return;
  if (state.mode === mode) return;
  state.mode = mode;
  if (root) root.dataset.codeMode = mode;
  notify({ kind: "mode" });
};

// GUI 同期の描画が成功したときに呼ぶ。編集中（mode が "edit"）は保持だけして、表示は更新しない（購読側が mode を見る）。
export const setGeneratedCode = (code, generation) => {
  state.generatedCode = code;
  state.generation = generation;
  notify({ kind: "generated" });
};
