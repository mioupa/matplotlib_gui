// プロット画像の表示。
export const showPlot = (dataUri, generation) => {
  const plotArea = document.getElementById("plotArea");
  if (!plotArea) return;
  const img = document.createElement("img");
  img.alt = "plot";
  img.src = dataUri;
  img.dataset.generation = String(generation);
  plotArea.replaceChildren(img);
};
