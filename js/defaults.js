// 設定オブジェクトの既定値。純粋な ES module（DOM に触れない）。
// py/mplgui/settings.py の default_settings() と同一でなければならない（tests/unit/test_defaults_parity.py が比較する）。

export const SCHEMA_VERSION = 4;

// UDカラーセット（系列の既定色の候補。この順で未使用の色を割り当てる）
export const PALETTE = [
  "#FF4B00",
  "#005AFF",
  "#03AF7A",
  "#4DC4FF",
  "#F6AA00",
  "#FFF100",
  "#990099",
  "#84919E",
  "#000000",
  "#804000",
  "#FF8082",
];

// エラーバー（片方向）の既定値。Y と X で別のオブジェクトにする（共有しない）
const defaultErrorSpec = () => ({ mode: "none", symmetric: true, value: null, valueMinus: null, column: "", columnMinus: "" });

// 軸ごとの目盛の既定値（X / Y / 第2Y 共通）
const defaultTicks = () => ({ majorStep: null, minorTicks: "auto", minorDivisions: null, tickFormat: "auto", tickDecimals: 1, inverted: false });

export const DEFAULT_SERIES = {
  id: "s1",
  x: "",
  y: "",
  color: "#FF4B00",
  lineWidth: 2,
  lineStyle: "solid",
  markerSize: null,
  label: "",
  secondaryAxis: false,
  source: "",
  errorBars: { y: defaultErrorSpec(), x: defaultErrorSpec(), capSize: 3 },
  marker: "auto",
  alpha: 1,
  fill: { lower: "", upper: "", alpha: 0.25 },
  colorColumn: "",
};

// 注釈（annotations[]）1つの既定値。id は追加するときに a1, a2, ... を振る（削除しても再利用しない）
export const DEFAULT_ANNOTATION = {
  id: "a1",
  kind: "hline",
  text: "",
  x: "",
  y: "",
  start: "",
  end: "",
  coords: "data",
  axis: "y",
  color: "#000000",
  lineStyle: "dashed",
  lineWidth: 1,
  alpha: null,
  fontSize: null,
  label: "",
};

// 近似曲線（fits[]）1つの既定値。id は f1, f2, ...。series は追加するときに系列1の id にする
export const DEFAULT_FIT = { id: "f1", series: "s1", model: "linear", degree: 2, show: "legend", color: "", lineStyle: "dashed" };

// 計算した列（computed[]）1つの既定値。id は追加するときに c1, c2, ... を振る（削除しても再利用しない）
export const DEFAULT_COMPUTED = { id: "", source: "", name: "", expr: "" };

export const DEFAULT_SETTINGS = {
  version: SCHEMA_VERSION,
  load: {
    delimiter: "",
    hasHeader: true,
    skipLines: 0,
    thousands: "",
    decimal: ".",
    comment: "",
    parseDates: true,
    files: [],
  },
  plot: {
    type: "line",
    skipRows: 0,
    xColumn: "",
    title: "",
    fontSize: 15,
    figure: { width: 8, height: 6, unit: "in" },
    latinFont: "default",
    palette: "ud",
    legend: { location: "best" },
    grid: { major: false, minor: false },
    margins: { left: null, right: null, bottom: null, top: null },
    spines: { top: true, right: true },
    step: { where: "post" },
    hist: { bins: null, density: false },
    colormap: "viridis",
    colorbarLabel: "",
  },
  axes: {
    x: { label: "", scale: "linear", min: null, max: null, dateFormat: "", ...defaultTicks(), majorStepUnit: "day", dateMin: "", dateMax: "" },
    y: { label: "", scale: "linear", min: null, max: null, ...defaultTicks() },
    y2: { label: "", scale: "linear", min: null, max: null, ...defaultTicks() },
  },
  series: [DEFAULT_SERIES],
  annotations: [],
  fits: [],
  computed: [],
  save: { filename: "", format: "png", transparent: false, dpi: 300, svgText: "path" },
};
