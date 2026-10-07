// データ確認タブの表（先頭100行。Python が返した preview ペイロードから組み立てる）。
const el = (tag, text) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
};

export const showPreview = (preview) => {
  const dataArea = document.getElementById("dataArea");
  if (!dataArea) return;
  const truncated = preview.truncated ? `（先頭${preview.limit}行のみ表示）` : "";
  const meta = el("div", `行数: ${preview.totalRows} / 列数: ${preview.totalColumns} ${truncated}`);
  meta.className = "data-meta";

  const table = el("table");
  table.border = "0";
  table.className = "dataframe data-table";
  const headRow = el("tr");
  for (const name of preview.columns) headRow.appendChild(el("th", name));
  table.appendChild(el("thead")).appendChild(headRow);
  const body = el("tbody");
  for (const row of preview.rows) {
    const tr = el("tr");
    for (const cell of row) tr.appendChild(el("td", cell));
    body.appendChild(tr);
  }
  table.appendChild(body);

  const wrap = el("div");
  wrap.className = "table-wrap";
  wrap.appendChild(table);
  dataArea.replaceChildren(meta, wrap);
};
