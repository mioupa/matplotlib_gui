// カラーパレット（系列の既定色）。純粋な ES module。選択肢の id は py/mplgui/settings.py の PALETTES と一致させる。
import { PALETTE as UD_PALETTE } from "./defaults.js";

export const PALETTES = {
  ud: UD_PALETTE,
  tab10: ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF"],
  gray: ["#000000", "#404040", "#707070", "#909090", "#B0B0B0"],
};

export const PALETTE_LABELS = { ud: "UD カラー", tab10: "tab10（matplotlib 標準）", gray: "グレースケール" };

export const getPalette = (id) => PALETTES[id] || PALETTES.ud;

// i 番目の系列の色（パレットを循環する）
export const paletteColor = (id, index) => {
  const colors = getPalette(id);
  return colors[index % colors.length];
};
