// 体裁セクション: スタイルプリセット、カラーパレット、図サイズの単位。
// 値は state に書き込む。プリセットの名前は設定に入れない（state.js が直近の適用を覚えるだけ）。
import { applyPalette, getSettings, setLastPreset, setPath, updateSeries } from "../state.js";
import { PRESETS, planPreset } from "../presets.js";
import { UNIT_NAMES, UNIT_STEP, convertLength } from "../units.js";
import { renderSeriesList } from "./series.js";
import { applyStateToForm } from "./forms.js";

const byId = (id) => document.getElementById(id);

// 図サイズの欄のラベルと step を、現在の単位に合わせる
export const syncFigureUnitView = () => {
  const unit = getSettings().plot.figure.unit;
  const name = UNIT_NAMES[unit] || unit;
  const select = byId("figUnit");
  if (select) select.value = unit;
  const width = byId("figWidth");
  const height = byId("figHeight");
  if (width) width.step = String(UNIT_STEP[unit]);
  if (height) height.step = String(UNIT_STEP[unit]);
  const wl = document.querySelector('label[for="figWidth"]');
  const hl = document.querySelector('label[for="figHeight"]');
  if (wl) wl.textContent = `図幅(${name})`;
  if (hl) hl.textContent = `図高さ(${name})`;
};

const onUnitChange = () => {
  const select = byId("figUnit");
  const { figure } = getSettings().plot;
  const to = select.value;
  const from = figure.unit;
  if (to === from) return;
  // 図の大きさ（物理サイズ）は変えず、数値だけ換算する。空欄・不正な入力はそのまま
  setPath("plot.figure.width", convertLength(figure.width, from, to));
  setPath("plot.figure.height", convertLength(figure.height, from, to));
  setPath("plot.figure.unit", to);
  for (const [id, key] of [["figWidth", "width"], ["figHeight", "height"]]) {
    const v = getSettings().plot.figure[key];
    if (typeof v === "number") byId(id).value = String(v);
  }
  syncFigureUnitView();
};

const applySelectedPreset = () => {
  const id = byId("stylePreset").value;
  const preset = PRESETS[id];
  if (!preset) return;
  const settings = getSettings();
  const plan = planPreset(preset, settings.plot.type, settings.series);
  setPath("plot.figure.width", plan.figure.width);
  setPath("plot.figure.height", plan.figure.height);
  setPath("plot.figure.unit", plan.figure.unit);
  setPath("plot.fontSize", plan.fontSize);
  for (const { id: seriesId, patch } of plan.series) updateSeries(seriesId, patch);
  setLastPreset(preset);
  applyStateToForm();
  syncFigureUnitView();
  renderSeriesList();
};

export const bindStyleSection = () => {
  const unit = byId("figUnit");
  if (unit) unit.addEventListener("change", onUnitChange);
  const apply = byId("applyPresetBtn");
  if (apply) apply.addEventListener("click", applySelectedPreset);
  const palette = byId("colorPalette");
  if (palette) palette.addEventListener("change", () => applyPalette(palette.value));
  syncFigureUnitView();
};
