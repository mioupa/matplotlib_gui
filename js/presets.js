// スタイルプリセット。純粋な ES module（DOM にも state にも触れない）。
// プリセットの名前は設定オブジェクトに入れない。適用すると、下の値が個別の設定に書き込まれる。
export const PRESETS = {
  standard: {
    label: "標準（8 × 6 inch、15 pt）",
    figure: { width: 8, height: 6, unit: "in" },
    fontSize: 15,
    lineWidth: 2,
    markerSize: null,
  },
  paper1: {
    label: "論文1段組（幅 8.5 cm、8 pt）",
    figure: { width: 8.5, height: 6.4, unit: "cm" },
    fontSize: 8,
    lineWidth: 1,
    markerSize: 9,
  },
  paper2: {
    label: "論文2段組（幅 17 cm、8 pt）",
    figure: { width: 17, height: 10, unit: "cm" },
    fontSize: 8,
    lineWidth: 1,
    markerSize: 9,
  },
  slide: {
    label: "スライド16:9（24 × 13.5 cm、18 pt）",
    figure: { width: 24, height: 13.5, unit: "cm" },
    fontSize: 18,
    lineWidth: 2.5,
    markerSize: 49,
  },
};

// プリセットを適用したときの変更内容を返す（設定は書き換えない）。
// 点サイズ: プリセットが null（自動）なら全系列を自動に戻す。数値なら、点を表示している系列
// （散布図、またはユーザーが数値を入れた系列）だけに設定し、自動のままの折れ線には点を出さない。
export const planPreset = (preset, plotType, series) => ({
  figure: { ...preset.figure },
  fontSize: preset.fontSize,
  series: series.map((s) => {
    const patch = { lineWidth: preset.lineWidth };
    if (preset.markerSize === null) patch.markerSize = null;
    else if (plotType === "scatter" || typeof s.markerSize === "number") patch.markerSize = preset.markerSize;
    return { id: s.id, patch };
  }),
});

// 最後に適用したプリセットがあるとき、新しい系列に与える既定値
export const newSeriesDefaults = (preset, plotType) => {
  if (!preset) return {};
  return {
    lineWidth: preset.lineWidth,
    markerSize: plotType === "scatter" && preset.markerSize !== null ? preset.markerSize : null,
  };
};
