// 起動・フォント取得の進捗バナー（#progress）と、描画中の表示（#renderBusy, aria-busy）。
export const showProgress = (text) => {
  const el = document.getElementById("progress");
  if (!el) return;
  if (document.documentElement.dataset.loadFailed) return; // 読み込み失敗の案内（index.html）を上書きしない
  el.textContent = text || "";
  el.hidden = !text;
};

export const setBusy = (busy, text = "描画中…") => {
  const overlay = document.getElementById("renderBusy");
  if (overlay) {
    overlay.hidden = !busy;
    overlay.textContent = text;
  }
  for (const id of ["plotPanel", "plotArea"]) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("aria-busy", busy ? "true" : "false");
  }
};
