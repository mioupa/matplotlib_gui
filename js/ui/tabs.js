// 「プロット / データ確認 / Pythonコード」のタブ切替（WAI-ARIA tabs。矢印キーでも移動できる）。
const TABS = [
  ["plot", "tabPlotBtn", "plotPanel"],
  ["data", "tabDataBtn", "dataPanel"],
  ["code", "tabCodeBtn", "codePanel"],
];

export const switchTab = (selected) => {
  for (const [name, btnId, panelId] of TABS) {
    const on = name === selected;
    const btn = document.getElementById(btnId);
    const panel = document.getElementById(panelId);
    if (btn) {
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
      btn.tabIndex = on ? 0 : -1;
    }
    if (panel) panel.classList.toggle("hidden", !on);
  }
};

export const bindTabs = () => {
  TABS.forEach(([name, btnId], idx) => {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener("click", () => switchTab(name));
    btn.addEventListener("keydown", (event) => {
      const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      event.preventDefault();
      const [nextName, nextBtnId] = TABS[(idx + step + TABS.length) % TABS.length];
      switchTab(nextName);
      document.getElementById(nextBtnId).focus();
    });
  });
  switchTab("plot");
};
