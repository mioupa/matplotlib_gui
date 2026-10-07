// ステータス表示。
export const setStatus = (message, isError = false, detail = "") => {
  const status = document.getElementById("status");
  if (status) {
    status.textContent = message || "";
    status.style.color = isError ? "var(--status-error)" : "var(--status-ok)";
  }

  const detailWrap = document.getElementById("statusDetailWrap");
  const detailEl = document.getElementById("statusDetail");
  if (!detailWrap || !detailEl) return;
  const normalized = typeof detail === "string" ? detail.trim() : "";
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
