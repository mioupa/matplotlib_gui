// 「プロット / データ確認 / Pythonコード(beta)」のタブ切替。
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
    if (btn) btn.classList.toggle("active", on);
    if (panel) panel.classList.toggle("hidden", !on);
  }
};

export const bindTabs = () => {
  for (const [name, btnId] of TABS) {
    const btn = document.getElementById(btnId);
    if (btn) btn.addEventListener("click", () => switchTab(name));
  }
  switchTab("plot");
};
