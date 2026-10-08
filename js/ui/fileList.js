// 読み込んだファイルの一覧（#fileList。2ファイル以上のときだけ表示）と、データ確認タブの表示切替（#previewSource）。
// 一覧は bridge.js が作る view model から描くだけ。操作（シート変更・削除）は handlers 経由で bridge.js に返す。
// file: {id, number, name, state: loading|ready|error, kind: "text"|"excel"|null, encoding, sheets, sheet, error, pasted}

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const kindText = (file) => {
  if (file.kind === "excel") return "Excel";
  return file.encoding ? `文字コード: ${file.encoding}` : "";
};

const buildRow = (file, handlers) => {
  const li = el("li", "file-row");
  li.id = `file-${file.id}`;
  li.dataset.state = file.state;
  li.appendChild(el("span", "file-row-no", `データ${file.number}`));
  const name = el("span", "file-row-name", file.pasted ? `貼り付けたデータ（${file.name}）` : file.name);
  name.title = file.name;
  li.appendChild(name);
  if (file.state === "loading") li.appendChild(el("span", "file-row-loading", "読み込み中…"));
  else if (file.state === "ready") li.appendChild(el("span", "file-row-kind", kindText(file)));
  if (file.state === "ready" && file.sheets.length > 0) {
    const select = el("select", "file-row-sheet");
    select.id = `file-${file.id}-sheet`;
    select.setAttribute("aria-label", `データ${file.number}のシート`);
    for (const sheetName of file.sheets) {
      const option = el("option", "", sheetName);
      option.value = sheetName;
      select.appendChild(option);
    }
    select.value = file.sheets.includes(file.sheet) ? file.sheet : file.sheets[0];
    select.addEventListener("change", () => handlers.onSheet(file.id, select.value));
    li.appendChild(select);
  }
  const remove = el("button", "small-btn ghost-btn", "削除");
  remove.type = "button";
  remove.id = `file-${file.id}-remove`;
  remove.setAttribute("aria-label", `データ${file.number}（${file.name}）を削除`);
  remove.addEventListener("click", () => handlers.onRemove(file.id));
  li.appendChild(remove);
  if (file.state === "error" && file.error) li.appendChild(el("div", "file-row-error", file.error));
  return li;
};

// files が 2 件以上のときだけ一覧を出す（1 件のときは従来の表示）
export const renderFileList = (files, handlers) => {
  const list = document.getElementById("fileList");
  if (!list) return;
  list.hidden = files.length < 2;
  list.replaceChildren(...(files.length < 2 ? [] : files.map((f) => buildRow(f, handlers))));
};

// データ確認タブの「表示するデータ」。files が 2 件以上のときだけ表示する
export const renderPreviewSource = (files, selectedId, onChange) => {
  const group = document.getElementById("previewSourceGroup");
  const select = document.getElementById("previewSource");
  if (!group || !select) return;
  group.hidden = files.length < 2;
  select.replaceChildren(
    ...files.map((f) => {
      const option = el("option", "", `データ${f.number}: ${f.name}`);
      option.value = f.id;
      return option;
    }),
  );
  if (files.length > 0) select.value = files.some((f) => f.id === selectedId) ? selectedId : files[0].id;
  select.onchange = () => onChange(select.value);
};
