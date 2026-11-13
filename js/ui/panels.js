// サブプロットのパネル（Phase 5e, G9）: 配置（行・列）、系列・注釈のパネルの選択、パネルごとのタイトル・軸ラベル。
// 表示の同期（syncPanels）は入力中の欄を作り直さない（computed.js の syncComputed と同じ考え方）。
import { getSettings, setPath, updateAnnotation, updatePanel, updateSeries } from "../state.js";
import { addNote } from "../bridge.js";
import { panelCount, planPanelRemap, usesY2 } from "../chart-types.js";
import { xAxisKind, yAxisKind } from "./series.js";

const esc = (text) =>
  String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// 画面の表示は 1 始まり: 「パネル1（1行目・1列目）」
export const panelName = (index, cols) => `パネル${index + 1}（${Math.floor(index / cols) + 1}行目・${(index % cols) + 1}列目）`;

const layoutKey = (layout) => `${layout.rows}x${layout.cols}`;

// 系列・注釈カードのパネルの選択（.series-panel / .annotation-panel）の選択肢と値、表示の有無を合わせる
export const syncPanelSelects = () => {
  const { plot, series, annotations } = getSettings();
  const n = panelCount(plot.layout);
  const key = layoutKey(plot.layout);
  const sync = (select, panel) => {
    const wrap = select.closest(".series-panel-wrap, .ann-panel-wrap");
    if (wrap) wrap.hidden = n < 2;
    if (select.dataset.layout !== key) {
      select.replaceChildren(
        ...Array.from({ length: n }, (_, i) => {
          const o = document.createElement("option");
          o.value = String(i);
          o.textContent = panelName(i, plot.layout.cols);
          return o;
        }),
      );
      select.dataset.layout = key;
    }
    if (document.activeElement !== select) select.value = String(panel ?? 0);
  };
  for (const item of document.querySelectorAll("#seriesList .series-item")) {
    const s = series.find((x) => x.id === item.dataset.seriesId);
    const select = item.querySelector(".series-panel");
    if (s && select) sync(select, s.panel);
  }
  for (const item of document.querySelectorAll("#annotationList .annotation-item")) {
    const a = annotations.find((x) => x.id === item.dataset.annId);
    const select = item.querySelector(".annotation-panel");
    if (a && select) sync(select, a.panel);
  }
};

const rowHtml = (i, cols, hasY2) => {
  const id = (name) => `panel-${i + 1}-${name}`;
  return `
    <div class="panel-label-row" data-panel-index="${i}">
      <div class="series-item-title">${esc(panelName(i, cols))}</div>
      <div class="group">
        <label for="${id("title")}">タイトル</label>
        <input id="${id("title")}" type="text" data-panel-field="title" />
      </div>
      <div class="row group">
        <div>
          <label for="${id("xlabel")}">X軸ラベル</label>
          <input id="${id("xlabel")}" type="text" data-panel-field="xLabel" />
        </div>
        <div>
          <label for="${id("ylabel")}">Y軸ラベル</label>
          <input id="${id("ylabel")}" type="text" data-panel-field="yLabel" />
        </div>
      </div>
      ${
        hasY2
          ? `<div class="group"><label for="${id("y2label")}">第2Y軸ラベル</label><input id="${id("y2label")}" type="text" data-panel-field="y2Label" /></div>`
          : ""
      }
    </div>`;
};

const syncPanelLabels = (multi) => {
  const { plot, axes, series } = getSettings();
  const group = document.getElementById("panelLabelsGroup");
  if (!group) return;
  group.hidden = !multi;
  if (!multi) return;
  const n = panelCount(plot.layout);
  const y2 = Array.from({ length: n }, (_, i) => usesY2(plot.type) && series.some((s) => s.secondaryAxis && (s.panel ?? 0) === i));
  const key = `${layoutKey(plot.layout)}|${y2.map(Number).join("")}`;
  const list = document.getElementById("panelLabelsList");
  if (list.dataset.key !== key) {
    list.innerHTML = Array.from({ length: n }, (_, i) => rowHtml(i, plot.layout.cols, y2[i])).join("");
    list.dataset.key = key;
  }
  const holders = { title: "なし", xLabel: axes.x.label || "自動", yLabel: axes.y.label || "自動", y2Label: axes.y2.label || "自動" };
  for (const input of list.querySelectorAll("[data-panel-field]")) {
    const i = Number(input.closest(".panel-label-row").dataset.panelIndex);
    const field = input.dataset.panelField;
    input.placeholder = holders[field];
    if (document.activeElement !== input) input.value = (plot.panels[i] && plot.panels[i][field]) || "";
  }
};

export const syncPanels = () => {
  const { plot } = getSettings();
  const multi = panelCount(plot.layout) > 1;
  for (const [id, value] of [["layoutRows", plot.layout.rows], ["layoutCols", plot.layout.cols]]) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = String(value);
  }
  const hide = (id, hidden) => {
    const el = document.getElementById(id);
    if (el) el.hidden = hidden;
  };
  hide("layoutOptionsGroup", !multi);
  hide("titlePanelHelp", !multi);
  // カテゴリの軸は共有できない（値は残す）
  const catX = xAxisKind() === "category";
  const catY = yAxisKind() === "category";
  const shareX = document.getElementById("layoutShareX");
  const shareY = document.getElementById("layoutShareY");
  if (shareX) shareX.disabled = catX;
  if (shareY) shareY.disabled = catY;
  hide("layoutShareHelp", !(multi && (catX || catY)));
  const help = document.getElementById("layoutShareHelp");
  if (help) help.textContent = `${[catX ? "X" : "", catY ? "Y" : ""].filter(Boolean).join("・")}軸はカテゴリなので共有できません（設定は残ります）。`;
  syncPanelLabels(multi);
  syncPanelSelects();
};

// パネルが減ったとき、範囲外のパネルを最後のパネルへ移し、画面の注意を添える（n が 1 のときは何も変えない）
export const applyPanelRemap = () => {
  const { plot, series, annotations } = getSettings();
  const n = panelCount(plot.layout);
  if (n < 2) return;
  const plan = planPanelRemap(series, annotations, n);
  for (const m of plan.series) {
    updateSeries(m.id, { panel: m.to }, "reconcile");
    addNote(`系列${m.index + 1}: パネル${m.from + 1}が無くなったため、パネル${m.to + 1}に移しました。`);
  }
  for (const m of plan.annotations) {
    updateAnnotation(m.id, { panel: m.to }, "reconcile");
    addNote(`注釈${m.index + 1}: パネル${m.from + 1}が無くなったため、パネル${m.to + 1}に移しました。`);
  }
};

export const bindPanels = () => {
  for (const [id, key] of [["layoutRows", "rows"], ["layoutCols", "cols"]]) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener("change", () => {
      setPath(`plot.layout.${key}`, Number(el.value));
      applyPanelRemap();
    });
  }
  const list = document.getElementById("panelLabelsList");
  if (list) {
    const onInput = (event) => {
      const target = event.target;
      if (!target || !target.dataset || !target.dataset.panelField) return;
      updatePanel(Number(target.closest(".panel-label-row").dataset.panelIndex), { [target.dataset.panelField]: target.value });
    };
    list.addEventListener("input", onInput);
    list.addEventListener("change", onInput);
  }
  syncPanels();
};
