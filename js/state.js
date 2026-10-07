// 設定オブジェクト（単一の正）。画面の入力はすべてここへ書き込み、描画・読込はここから JSON を作る。
// DOM には触れない。変更は subscribe で購読する。
import { DEFAULT_SERIES, DEFAULT_SETTINGS, PALETTE } from "./defaults.js";

const clone = (value) => JSON.parse(JSON.stringify(value));

let settings = clone(DEFAULT_SETTINGS);
let seriesCounter = 1; // 系列 id は連番で払い出し、削除しても再利用しない
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

// 既定色: パレットのうち未使用の最初の色。すべて使用済みなら系列数で循環する。
export const nextSeriesColor = () => {
  const used = new Set(settings.series.map((s) => String(s.color).toUpperCase()));
  const free = PALETTE.find((c) => !used.has(c.toUpperCase()));
  return free || PALETTE[settings.series.length % PALETTE.length];
};

export const addSeries = (preset = {}) => {
  seriesCounter += 1;
  const series = { ...clone(DEFAULT_SERIES), color: nextSeriesColor(), ...preset, id: `s${seriesCounter}` };
  settings.series.push(series);
  notify({ kind: "series-list", origin: "user" });
  return series;
};

export const removeSeries = (id) => {
  if (settings.series.length <= 1) return;
  const idx = settings.series.findIndex((s) => s.id === id);
  if (idx < 0) return;
  settings.series.splice(idx, 1);
  notify({ kind: "series-list", origin: "user" });
};

export const hasSecondaryAxis = () => settings.series.some((s) => s.secondaryAxis);
