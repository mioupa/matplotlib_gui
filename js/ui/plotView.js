// プロット画像の表示。summary（図の要約。runner.figure_summary）は E2E のために data-summary に JSON で持たせる。
export const showPlot = (dataUri, generation, summary) => {
  const plotArea = document.getElementById("plotArea");
  if (!plotArea) return;
  const img = document.createElement("img");
  img.alt = "plot";
  img.src = dataUri;
  img.dataset.generation = String(generation);
  if (summary !== undefined) img.dataset.summary = JSON.stringify(summary);
  plotArea.replaceChildren(img);
};
