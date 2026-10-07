// ステータス表示（#status）。種別: ok（成功）/ warning（警告）/ error（エラー）/ info（進行中など）。
// 日本語フォント取得失敗のような「セッション中ずっと有効な警告」は sticky として保持し、後続の表示にも添える。
const stickyWarnings = [];
let last = { message: "", kind: "", detail: "", warnings: [] };

const paint = () => {
  const status = document.getElementById("status");
  if (status) {
    const warnings = [...last.warnings, ...stickyWarnings];
    let kind = last.kind;
    if (kind !== "error" && warnings.length > 0) kind = "warning";
    if (!last.message && warnings.length === 0) kind = "";
    status.dataset.kind = kind;
    status.replaceChildren();
    if (last.message) status.appendChild(document.createTextNode(last.message));
    for (const text of warnings) {
      const item = document.createElement("div");
      item.className = "status-warning-item";
      item.textContent = text;
      status.appendChild(item);
    }
  }

  const detailWrap = document.getElementById("statusDetailWrap");
  const detailEl = document.getElementById("statusDetail");
  if (!detailWrap || !detailEl) return;
  const normalized = typeof last.detail === "string" ? last.detail.trim() : "";
  if (normalized) {
    detailEl.textContent = normalized;
    detailWrap.classList.remove("hidden");
    detailWrap.open = true;
  } else {
    detailEl.textContent = "";
    detailWrap.classList.add("hidden");
    detailWrap.open = false;
  }
};

// warnings: 文字列の配列（成功メッセージと一緒に警告として表示する）
export const setStatus = (message, kind = "ok", detail = "", warnings = []) => {
  last = { message: message || "", kind, detail, warnings };
  paint();
};

export const addStickyWarning = (message) => {
  if (!stickyWarnings.includes(message)) stickyWarnings.push(message);
  paint();
};

// {message, series?} の配列 → 表示用の文字列配列
export const warningTexts = (warnings) => (warnings || []).map((w) => (typeof w === "string" ? w : w.message)).filter(Boolean);
