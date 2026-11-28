const editor = document.querySelector("#data-editor");
const rows = editor.querySelector("tbody");
const template = document.querySelector("#editor-row");
let dirty = false;

function addRow() {
  rows.append(template.content.cloneNode(true));
  dirty = true;
  return rows.lastElementChild;
}

document.querySelector("#add-row").addEventListener("click", () => {
  addRow().querySelector("input").focus();
});
editor.addEventListener("click", (event) => {
  if (event.target.matches("[data-remove]")) {
    event.target.closest("tr").remove();
    dirty = true;
  }
});
editor.addEventListener("input", () => { dirty = true; });
editor.addEventListener("submit", () => { dirty = false; });
window.addEventListener("beforeunload", (event) => {
  if (dirty) event.preventDefault();
});

rows.addEventListener("paste", (event) => {
  if (!event.target.matches("input")) return;
  const text = event.clipboardData.getData("text/plain").replace(/\r\n/g, "\n").replace(/\n$/, "");
  if (!text.includes("\t") && !text.includes("\n")) return;
  const paste = text.split("\n").map((line) => line.split("\t"));
  const startRow = event.target.closest("tr").sectionRowIndex;
  const startCol = event.target.closest("td").cellIndex;
  const width = template.content.querySelectorAll("input").length;
  event.preventDefault();
  if (startRow + paste.length > 19999 ||
      paste.some((row) => startCol + row.length > width || row.some((value) => value.length > 500))) {
    window.alert("Vùng dán vượt số cột, dòng hoặc độ dài ô được hỗ trợ.");
    return;
  }
  for (const [offset, values] of paste.entries()) {
    const target = rows.rows[startRow + offset] || addRow();
    for (const [column, value] of values.entries()) {
      target.cells[startCol + column].querySelector("input").value = value;
    }
  }
  dirty = true;
});
