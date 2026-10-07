// 「実行結果」欄（#codeOutput）。print / stderr の出力と、失敗時のトレースバックを表示する。
// 空のときは CSS（:empty）が「（出力はありません）」を出す。
export const showCodeOutput = ({ output = "", traceback = "", kind = "ok" } = {}) => {
  const el = document.getElementById("codeOutput");
  if (!el) return;
  const parts = [String(output || "").replace(/\s+$/, ""), String(traceback || "").replace(/\s+$/, "")].filter(Boolean);
  const text = parts.join("\n\n");
  el.dataset.kind = kind === "error" ? "error" : "ok";
  if (text) el.textContent = text;
  else el.replaceChildren();
};
