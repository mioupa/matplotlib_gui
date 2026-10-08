// データ確認タブの表（先頭100行。Python が返した preview ペイロードから組み立てる）。
const el = (tag, text) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
};

// skipRows として有効な値（正の整数）だけを行数にする。不正値・空は 0 とみなす
const effectiveSkipRows = (value) => (Number.isInteger(value) && value > 0 ? value : 0);

// 描画から除外される先頭 skipRows 行（データ行。ヘッダは数えない）に .skipped-row を付ける。Python は呼ばない。
export const applySkipRows = (skipRows) => {
  const n = effectiveSkipRows(skipRows);
  const rows = document.querySelectorAll("#dataArea tbody tr");
  rows.forEach((tr, idx) => tr.classList.toggle("skipped-row", idx < n));
};

// ヘッダより前に読み飛ばした行（preamble: {lines, total}）。表の上に、枠で囲んで等幅で出す
const preambleBox = (preamble) => {
  if (!preamble || !(preamble.total > 0)) return null;
  const box = el("div");
  box.id = "dataPreamble";
  box.appendChild(el("div", `ヘッダより前に読み飛ばした行（${preamble.total}行）`)).className = "preamble-title";
  box.appendChild(el("pre", preamble.lines.join("\n"))).className = "preamble-lines";
  const more = preamble.total - preamble.lines.length;
  if (more > 0) box.appendChild(el("div", `…ほか ${more} 行`)).className = "preamble-more";
  return box;
};

export const showPreview = (preview, skipRows = 0) => {
  const dataArea = document.getElementById("dataArea");
  if (!dataArea) return;
  const truncated = preview.truncated ? `（先頭${preview.limit}行のみ表示）` : "";
  const meta = el("div", `行数: ${preview.totalRows} / 列数: ${preview.totalColumns} ${truncated}`);
  meta.className = "data-meta";

  const table = el("table");
  table.border = "0";
  table.className = "dataframe data-table";
  const headRow = el("tr");
  const numHead = el("th", "#");
  numHead.className = "row-number";
  headRow.appendChild(numHead);
  for (const name of preview.columns) headRow.appendChild(el("th", name));
  table.appendChild(el("thead")).appendChild(headRow);
  const body = el("tbody");
  preview.rows.forEach((row, idx) => {
    const tr = el("tr");
    const num = el("td", String(idx + 1)); // 1 始まりのデータ行番号
    num.className = "row-number";
    tr.appendChild(num);
    for (const cell of row) tr.appendChild(el("td", cell));
    body.appendChild(tr);
  });
  table.appendChild(body);

  const wrap = el("div");
  wrap.className = "table-wrap";
  wrap.appendChild(table);
  dataArea.replaceChildren(...[preambleBox(preview.preamble), meta, wrap].filter(Boolean));
  applySkipRows(skipRows);
};
