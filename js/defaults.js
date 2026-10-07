// 設定オブジェクトの既定値。純粋な ES module（DOM に触れない）。
// py/mplgui/settings.py の default_settings() と同一でなければならない（tests/unit/test_defaults_parity.py が比較する）。

export const SCHEMA_VERSION = 1;

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
};

export const DEFAULT_SETTINGS = {
  version: SCHEMA_VERSION,
  load: { delimiter: "", hasHeader: true },
  plot: {
    type: "line",
    skipRows: 0,
    xColumn: "",
    title: "",
    fontSize: 15,
    figure: { width: 8, height: 6 },
    legend: { location: "best" },
    grid: { major: false, minor: false },
    margins: { left: null, right: null, bottom: null, top: null },
  },
  axes: {
    x: { label: "", scale: "linear", min: null, max: null },
    y: { label: "", scale: "linear", min: null, max: null },
    y2: { label: "", scale: "linear", min: null, max: null },
  },
  series: [DEFAULT_SERIES],
  save: { filename: "", format: "png", transparent: false },
};
