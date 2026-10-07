// 画面の入力欄 ⇄ 設定オブジェクトの対応表。入力は state に書き込み、初期表示は state から描く。
import { getPath, setPath } from "../state.js";

// [要素 id, 設定のパス, 種別]
export const FIELDS = [
  ["delimiter", "load.delimiter", "text"],
  ["hasHeader", "load.hasHeader", "checkbox"],
  ["plotType", "plot.type", "select"],
  ["skipRows", "plot.skipRows", "number"],
  ["xColumn", "plot.xColumn", "select"],
  ["title", "plot.title", "text"],
  ["xLabel", "axes.x.label", "text"],
  ["yLabel", "axes.y.label", "text"],
  ["y2Label", "axes.y2.label", "text"],
  ["xScale", "axes.x.scale", "select"],
  ["xMin", "axes.x.min", "number"],
  ["xMax", "axes.x.max", "number"],
  ["yScale", "axes.y.scale", "select"],
  ["yMin", "axes.y.min", "number"],
  ["yMax", "axes.y.max", "number"],
  ["y2Scale", "axes.y2.scale", "select"],
  ["y2Min", "axes.y2.min", "number"],
  ["y2Max", "axes.y2.max", "number"],
  ["latinFont", "plot.latinFont", "select"],
  ["fontSize", "plot.fontSize", "number"],
  ["showMajorGrid", "plot.grid.major", "checkbox"],
  ["showMinorGrid", "plot.grid.minor", "checkbox"],
  ["legendLocation", "plot.legend.location", "select"],
  ["figWidth", "plot.figure.width", "number"],
  ["figHeight", "plot.figure.height", "number"],
  ["subplotLeft", "plot.margins.left", "number"],
  ["subplotRight", "plot.margins.right", "number"],
  ["subplotBottom", "plot.margins.bottom", "number"],
  ["subplotTop", "plot.margins.top", "number"],
  ["saveFilename", "save.filename", "text"],
  ["saveTransparent", "save.transparent", "checkbox"],
  ["saveFormat", "save.format", "select"],
  ["svgText", "save.svgText", "select"],
];

// 数値欄: 空 → null、数値 → number、数値にならない入力 → 文字列のまま（Python が日本語のエラーにする）
export const readNumber = (input) => {
  if (input.validity && input.validity.badInput) return "invalid";
  const raw = input.value.trim();
  if (raw === "") return null;
  const num = Number(raw);
  return Number.isFinite(num) ? num : raw;
};

export const readField = (el, kind) => {
  if (kind === "checkbox") return el.checked;
  if (kind === "number") return readNumber(el);
  return el.value;
};

const writeField = (el, kind, value) => {
  if (kind === "checkbox") el.checked = !!value;
  else el.value = value === null || value === undefined ? "" : String(value);
};

// state → 画面（初期表示用。入力中の欄を書き換えないよう、通常の入力では呼ばない）
export const applyStateToForm = () => {
  for (const [id, path, kind] of FIELDS) {
    const el = document.getElementById(id);
    if (el) writeField(el, kind, getPath(path));
  }
};

export const bindForms = () => {
  for (const [id, path, kind] of FIELDS) {
    const el = document.getElementById(id);
    if (!el) continue;
    const onEdit = () => setPath(path, readField(el, kind));
    el.addEventListener("input", onEdit);
    el.addEventListener("change", onEdit);
  }
};
