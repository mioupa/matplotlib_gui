// 設定オブジェクト（単一の正）。画面の入力はすべてここへ書き込み、描画・読込はここから JSON を作る。
// DOM には触れない。変更は subscribe で購読する。
import { DEFAULT_ANNOTATION, DEFAULT_FIT, DEFAULT_SERIES, DEFAULT_SETTINGS } from "./defaults.js";
import { getPalette, paletteColor } from "./palettes.js";
import { usesY2 } from "./chart-types.js";
import { newSeriesDefaults } from "./presets.js";

const clone = (value) => JSON.parse(JSON.stringify(value));

let settings = clone(DEFAULT_SETTINGS);
let lastPreset = null; // 最後に適用したスタイルプリセット（このセッションの間だけ。設定オブジェクトには入れない）
let seriesCounter = 1; // 系列 id は連番で払い出し、削除しても再利用しない
let annotationCounter = 0; // 注釈 id（a1, a2, ...）。削除しても再利用しない
let fitCounter = 0; // 近似曲線 id（f1, f2, ...）。削除しても再利用しない
const listeners = new Set();

export const getSettings = () => settings;
export const toJson = () => JSON.stringify(settings);

export const subscribe = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

const notify = (change) => {
  for (const fn of Array.from(listeners)) fn(settings, change);
};

// "plot.figure.width" のようなパスの値を返す
export const getPath = (path, source = settings) => path.split(".").reduce((obj, key) => (obj == null ? undefined : obj[key]), source);

const assign = (target, path, value) => {
  const keys = path.split(".");
  const last = keys.pop();
  let obj = target;
  for (const key of keys) obj = obj[key];
  obj[last] = value;
};

// origin: "user"（既定。変更の通知先で再描画等を予約する）| "reconcile"（読込後の整合のため。再描画は呼び出し側が行う）
export const setPath = (path, value, origin = "user") => {
  if (getPath(path) === value) return;
  assign(settings, path, value);
  notify({ kind: "path", path, origin });
};

// 読み込むファイル（load.files）の sheet を替える。通知は load.files の変更（読み直しのきっかけ）
export const setFileSheet = (id, sheet, origin = "user") => {
  const file = settings.load.files.find((f) => f.id === id);
  if (!file || file.sheet === sheet) return;
  file.sheet = sheet;
  notify({ kind: "path", path: "load.files", origin, fileId: id });
};

const findSeries = (id) => settings.series.find((s) => s.id === id);

export const updateSeries = (id, patch, origin = "user") => {
  const series = findSeries(id);
  if (!series) return;
  let changed = false;
  for (const [key, value] of Object.entries(patch)) {
    if (series[key] !== value) {
      series[key] = value;
      changed = true;
    }
  }
  if (changed) notify({ kind: "series-field", id, fields: Object.keys(patch), origin });
};

// 既定色: 現在のパレットのうち未使用の最初の色。すべて使用済みなら系列数で循環する。
export const nextSeriesColor = () => {
  const palette = getPalette(settings.plot.palette);
  const used = new Set(settings.series.map((s) => String(s.color).toUpperCase()));
  const free = palette.find((c) => !used.has(c.toUpperCase()));
  return free || palette[settings.series.length % palette.length];
};

// パレットを替え、すべての系列を系列の順に新しいパレットの色で塗り直す（個別に選んだ色も上書きする）。
// パレットの変更を最後に通知するので、購読側は塗り直し後の色で画面を描ける。
export const applyPalette = (id) => {
  settings.series.forEach((s, i) => updateSeries(s.id, { color: paletteColor(id, i) }));
  setPath("plot.palette", id);
};

export const setLastPreset = (preset) => {
  lastPreset = preset;
};
export const getLastPreset = () => lastPreset;

export const addSeries = (overrides = {}) => {
  seriesCounter += 1;
  const series = {
    ...clone(DEFAULT_SERIES),
    color: nextSeriesColor(),
    ...newSeriesDefaults(lastPreset, settings.plot.type),
    ...overrides,
    id: `s${seriesCounter}`,
  };
  settings.series.push(series);
  notify({ kind: "series-list", origin: "user" });
  return series;
};

// 系列を削除する。その系列の近似曲線も消す（消した近似曲線の数を返す。系列が1つだけなら削除せず -1）
export const removeSeries = (id) => {
  if (settings.series.length <= 1) return -1;
  const idx = settings.series.findIndex((s) => s.id === id);
  if (idx < 0) return -1;
  settings.series.splice(idx, 1);
  const before = settings.fits.length;
  settings.fits = settings.fits.filter((f) => f.series !== id);
  const removedFits = before - settings.fits.length;
  notify({ kind: "series-list", origin: "user" });
  if (removedFits > 0) notify({ kind: "fit-list", origin: "user" });
  return removedFits;
};

// 系列を delta（-1 で前、+1 で後ろ）だけ動かす。端では何もしない
export const moveSeries = (id, delta) => {
  const idx = settings.series.findIndex((s) => s.id === id);
  const to = idx + delta;
  if (idx < 0 || to < 0 || to >= settings.series.length) return;
  const [item] = settings.series.splice(idx, 1);
  settings.series.splice(to, 0, item);
  notify({ kind: "series-list", origin: "user" });
};

// 系列の複製: すべての設定を写し、id は新しく、色は現在のパレットの未使用の色にして、元の系列の直後に入れる（近似曲線は写さない）
export const duplicateSeries = (id) => {
  const idx = settings.series.findIndex((s) => s.id === id);
  if (idx < 0) return null;
  seriesCounter += 1;
  const copy = { ...clone(settings.series[idx]), id: `s${seriesCounter}`, color: nextSeriesColor() };
  settings.series.splice(idx + 1, 0, copy);
  notify({ kind: "series-list", origin: "user" });
  return copy;
};

// ---- 注釈・近似曲線 ----
export const addAnnotation = () => {
  annotationCounter += 1;
  const item = { ...clone(DEFAULT_ANNOTATION), id: `a${annotationCounter}` };
  settings.annotations.push(item);
  notify({ kind: "annotation-list", origin: "user" });
  return item;
};

export const updateAnnotation = (id, patch, origin = "user") => {
  const item = settings.annotations.find((a) => a.id === id);
  if (!item) return;
  let changed = false;
  for (const [key, value] of Object.entries(patch)) {
    if (item[key] !== value) {
      item[key] = value;
      changed = true;
    }
  }
  if (changed) notify({ kind: "annotation-field", id, fields: Object.keys(patch), origin });
};

export const removeAnnotation = (id) => {
  const idx = settings.annotations.findIndex((a) => a.id === id);
  if (idx < 0) return;
  settings.annotations.splice(idx, 1);
  notify({ kind: "annotation-list", origin: "user" });
};

export const addFit = () => {
  fitCounter += 1;
  const first = settings.series[0];
  const item = { ...clone(DEFAULT_FIT), id: `f${fitCounter}`, series: first ? first.id : DEFAULT_FIT.series };
  settings.fits.push(item);
  notify({ kind: "fit-list", origin: "user" });
  return item;
};

export const updateFit = (id, patch, origin = "user") => {
  const item = settings.fits.find((f) => f.id === id);
  if (!item) return;
  let changed = false;
  for (const [key, value] of Object.entries(patch)) {
    if (item[key] !== value) {
      item[key] = value;
      changed = true;
    }
  }
  if (changed) notify({ kind: "fit-field", id, fields: Object.keys(patch), origin });
};

export const removeFit = (id) => {
  const idx = settings.fits.findIndex((f) => f.id === id);
  if (idx < 0) return;
  settings.fits.splice(idx, 1);
  notify({ kind: "fit-list", origin: "user" });
};

export const hasSecondaryAxis = () => usesY2(settings.plot.type) && settings.series.some((s) => s.secondaryAxis); // 第2Y軸を使わない種類では、値を残しても使わない
