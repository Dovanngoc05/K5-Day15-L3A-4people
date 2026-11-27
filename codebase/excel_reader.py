"""Read multiple local Excel files or uploaded binary streams without changing sources.

This is an ingestion layer: it preserves sheets and cell references, and does not
infer headers, merge conflicting schedules, or decide which source is authoritative.
"""
import argparse
from datetime import date, datetime, time, timedelta
from io import BytesIO
import json
from pathlib import Path


SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}


def _json_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _read_workbook(source, max_cells):
    from openpyxl import load_workbook

    if isinstance(source, (str, Path)):
        path = Path(source)
        name = path.name
        location = str(path.resolve())
        payload = path.read_bytes()
    else:
        name = Path(str(getattr(source, "name", "uploaded.xlsx"))).name
        location = name
        # UploadedFile and BytesIO both offer getvalue(), independent of cursor.
        if hasattr(source, "getvalue"):
            payload = source.getvalue()
        else:
            position = source.tell()
            try:
                source.seek(0)
                payload = source.read()
            finally:
                source.seek(position)
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Chi ho tro .xlsx va .xlsm; hay chuyen .xls sang .xlsx.")
    book = cached = None
    try:
        book = load_workbook(BytesIO(payload), data_only=False, keep_links=False)
        cached = load_workbook(BytesIO(payload), data_only=True, keep_links=False)
        area = sum(sheet.max_row * sheet.max_column for sheet in book)
        if area > max_cells:
            raise ValueError("Workbook vuot gioi han %d o (%d o)." % (max_cells, area))
        sheets = []
        for sheet in book:
            inherited = {}
            for merged in sheet.merged_cells.ranges:
                anchor = sheet.cell(merged.min_row, merged.min_col).coordinate
                for row in range(merged.min_row, merged.max_row + 1):
                    for col in range(merged.min_col, merged.max_col + 1):
                        inherited[(row, col)] = anchor
            rows = []
            warnings = []
            for row in sheet.iter_rows():
                cells = []
                for cell in row:
                    anchor = inherited.get((cell.row, cell.column), cell.coordinate)
                    original = sheet[anchor]
                    formula = original.data_type == "f"
                    value = cached[sheet.title][anchor].value if formula else original.value
                    if value is None and not formula:
                        continue
                    if formula and value is None and cell.coordinate == anchor:
                        warnings.append("%s: cong thuc chua co ket qua cache; khong tu tinh." % anchor)
                    cells.append({
                        "coordinate": cell.coordinate,
                        "source_cell": anchor,
                        "inherited": anchor != cell.coordinate,
                        "value": _json_value(value),
                        "formula": _json_value(original.value) if formula else None,
                        "hyperlink": original.hyperlink.target if original.hyperlink else None,
                    })
                if cells:
                    rows.append({"row_number": row[0].row, "cells": cells})
            sheets.append({
                "name": sheet.title,
                "state": sheet.sheet_state,
                "merged_ranges": sorted(str(r) for r in sheet.merged_cells.ranges),
                "rows": rows,
                "warnings": warnings,
            })
        return {"name": name, "location": location, "sheets": sheets}
    finally:
        if book is not None:
            book.close()
        if cached is not None:
            cached.close()


def read_excel_files(sources, *, max_cells=500_000):
    """Read an iterable of paths or binary uploads, with errors isolated per file.

    Returns JSON-compatible {files, errors, summary}. Merged-cell values are
    repeated only inside their actual merge range and retain the anchor address.
    Files with the same name remain separate, identified by source_id.
    No writes, network requests, model calls, or external effects.
    """
    if max_cells <= 0:
        raise ValueError("max_cells must be positive")
    if isinstance(sources, (str, Path)) or hasattr(sources, "read"):
        sources = [sources]
    result = {"files": [], "errors": []}
    for index, source in enumerate(sources, start=1):
        source_id = "file-%d" % index
        name = str(source) if isinstance(source, (str, Path)) else str(getattr(source, "name", "uploaded.xlsx"))
        try:
            workbook = _read_workbook(source, max_cells)
            workbook["source_id"] = source_id
            result["files"].append(workbook)
        except Exception as exc:
            result["errors"].append({"source_id": source_id, "file": name,
                                     "error": "%s: %s" % (type(exc).__name__, exc)})
    result["summary"] = {
        "files_read": len(result["files"]),
        "files_failed": len(result["errors"]),
        "sheets_read": sum(len(f["sheets"]) for f in result["files"]),
        "rows_read": sum(len(s["rows"]) for f in result["files"] for s in f["sheets"]),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Doc nhieu file Excel A5; khong sua file goc.")
    parser.add_argument("paths", nargs="+", help="File Excel hoac thu muc (khong quet thu muc con)")
    parser.add_argument("--output", type=Path, help="Luu JSON; nen dat trong data-btc/")
    args = parser.parse_args()
    paths = []
    for name in args.paths:
        path = Path(name)
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir()
                                if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("~$")))
        else:
            paths.append(path)
    if not paths:
        parser.error("Khong tim thay file Excel nao.")
    if args.output:
        if args.output.exists():
            parser.error("File output da ton tai; hay chon ten moi.")
        if args.output.suffix.lower() != ".json":
            parser.error("Output phai co duoi .json.")
    result = read_excel_files(paths)
    print(json.dumps(result["summary"], ensure_ascii=True))
    for file in result["files"]:
        print("%s: %s (%d sheets)" % (file["source_id"], file["name"], len(file["sheets"])))
    for error in result["errors"]:
        print("ERROR %s: %s" % (error["file"], error["error"]))
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
        print("Saved: %s" % args.output)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
