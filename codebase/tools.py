"""Công cụ của bài toán — NHÓM VIẾT. Điền ở guide bước 2.2 (thiết kế) và 3.2 (code).

Mỗi công cụ là một hàm Python có @tool. Docstring ghi đúng 4 ý như sơ đồ ở spec.md §4:
    tên · input · output · có tác động ra ngoài không (gửi tin, sửa dữ liệu, chấm điểm…)
Khung tự ghi mỗi lần gọi công cụ vào trace (tên, input, output rút gọn, thời gian, lỗi).

Số công cụ, kiểu công cụ do thiết kế của nhóm quyết định — có bài chỉ cần một công cụ tra cứu.
Công cụ có tác động ra ngoài: KHÔNG tự làm. Trả về bản nháp chờ người duyệt (guide bước 2.2, "chỗ người duyệt").
Dữ liệu công cụ đọc (bài mẫu, thông báo mẫu, lịch…): để trong data/ và mô tả ở data/DATA_CARD.md.
"""
from tracing import tool, TOOLS  # noqa: F401  (TOOLS: danh sách công cụ đã đăng ký, dùng khi viết vòng lặp agent)
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import re
import unicodedata


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _fold(value):
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _query_dates(query):
    found = set()
    for value in re.findall(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b", query):
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d" if "-" in value else "%d/%m/%Y")
            found.add(parsed.date().isoformat())
        except ValueError:
            continue
    return found


@lru_cache(maxsize=4)
def _read_schedule_workbooks(names):
    from excel_reader import read_excel_files

    paths = [DATA_DIR / name for name in names if (DATA_DIR / name).is_file()]
    return read_excel_files(paths)


@tool
def search_schedule_sources(query: str) -> dict:
    """Tra bằng chứng lịch trong workbook local theo ngày/lớp/buổi.
    Input: câu hỏi lịch (str). Output: các dòng Excel khớp cùng tên file/sheet/ô nguồn.
    Chỉ đọc allowlist trong data/, giới hạn learners.xlsx ở hàng tiêu đề; không ghi hay gửi dữ liệu ra ngoài.
    """
    query_text = str(query or "")
    folded = _fold(query_text)
    fixture_ids = re.findall(r"\[(?:LICH|CA|KT|GHICHU)-[A-Z0-9-]+\]", query_text, re.IGNORECASE)
    if fixture_ids:
        return {"evidence": [], "errors": [],
                "notice": "Dữ kiện nằm trong fixture của câu hỏi; trích đúng mã fixture, không coi là workbook."}

    dates = _query_dates(query_text)
    classes = set(re.findall(r"\bL[23](?:AB|A|B)\b", query_text.upper()))
    sessions = {re.sub(r"\s+", " ", value).upper()
                for value in re.findall(r"\b(?:LAB|LEC)\s*\d+\b", query_text, re.IGNORECASE)}
    explicit_rows = set()
    for match in re.finditer(r"\bdong\s+(\d+)(?:\s*[-–]\s*(\d+)|\s+va\s+(\d+))?", folded):
        start = int(match.group(1))
        end = int(match.group(2) or match.group(3) or start)
        if end - start <= 100:
            explicit_rows.update(range(start, end + 1))
    cell_refs = []
    for first, last in re.findall(r"\b([A-Z]{1,3}\d+)\s*:\s*([A-Z]{1,3}\d+)\b", query_text.upper()):
        cell_refs.extend((first, last))
    for group in re.findall(r"\b[A-Z]{1,3}\d+(?:\s*/\s*[A-Z]{1,3}\d+)+", query_text.upper()):
        cell_refs.extend(re.findall(r"[A-Z]{1,3}\d+", group))
    cell_refs.extend(re.findall(r"\b(?:ô|cell|phòng)\s+([A-Z]{1,3}\d+)\b", query_text, re.IGNORECASE))
    explicit_rows.update(int(re.search(r"\d+", cell).group()) for cell in cell_refs)
    learner_query = any(term in folded for term in
                        ("learners.xlsx", "student_id", "ma sinh vien", "anh xa hoc vien", "danh sach hoc vien"))
    known_files = ("teaching-schedule.xlsx", "lab-coach-schedule.xlsx", "learners.xlsx")
    mentioned_files = tuple(name for name in known_files if name in query_text.casefold())
    if mentioned_files:
        filenames = tuple(name for name in mentioned_files if name != "learners.xlsx" or learner_query)
    else:
        filenames = ("teaching-schedule.xlsx", "lab-coach-schedule.xlsx")
        if learner_query:
            filenames += ("learners.xlsx",)
    result = _read_schedule_workbooks(filenames)
    evidence = []
    errors = [{"file": Path(item["file"]).name, "error": item["error"]}
              for item in result.get("errors", [])]
    known_sheets = ("Khoá 9 (GĐ1)", "Lịch sử chỉnh sửa", "Tong_hop", "Dang_ky_chi_tiet",
                    "Đổi buổi", "Lịch lab 2604-0805", "Lịch lớp K9 (bản chép)")
    named_sheets = [name for name in known_sheets if _fold(name) in folded]

    for workbook in result.get("files", []):
        filename = workbook["name"]
        for sheet in workbook.get("sheets", []):
            sheet_name = sheet["name"]
            if filename.casefold() == "learners.xlsx":
                # Header only: never forward student names or IDs to the model.
                for row in sheet.get("rows", []):
                    if row["row_number"] == 1:
                        cells = [{"cell": c["source_cell"], "value": str(c["value"])[:160]}
                                 for c in row["cells"] if c.get("value") is not None]
                        evidence.append((200, {"file": "data/learners.xlsx", "sheet": sheet_name,
                                               "row": 1, "cells": cells,
                                               "note": "Chỉ có header; không có ánh xạ lớp/nhóm/phòng."}))
                        break
                continue

            sheet_folded = _fold(sheet_name)
            sheet_mentioned = bool(sheet_folded and sheet_folded in folded)
            if named_sheets:
                if not sheet_mentioned:
                    is_comparison_source = (
                        "teaching-schedule.xlsx" in mentioned_files and
                        "lab-coach-schedule.xlsx" in mentioned_files and
                        ((filename == "teaching-schedule.xlsx" and sheet_name == "Khoá 9 (GĐ1)") or
                         (filename == "lab-coach-schedule.xlsx" and
                          (sheet_name == "Lịch lớp K9 (bản chép)" and "ban chep" in folded)))
                    )
                    if not is_comparison_source:
                        continue
            elif filename == "teaching-schedule.xlsx" and "teaching-schedule.xlsx" in mentioned_files:
                if sheet_name != "Khoá 9 (GĐ1)":
                    continue
            is_change_log = any(term in sheet_folded for term in ("lich su", "doi buoi", "doi ca"))
            for row in sheet.get("rows", []):
                cells = row.get("cells", [])
                row_number = row["row_number"]
                explicitly_requested = row_number in explicit_rows
                row_text = " ".join(str(cell.get("value", "")) for cell in cells)
                row_dates = _query_dates(row_text)
                row_classes = set(re.findall(r"\bL[23](?:AB|A|B)\b", row_text.upper()))
                row_sessions = {re.sub(r"\s+", " ", value).upper()
                                for value in re.findall(r"\b(?:LAB|LEC)\s*\d+\b", row_text, re.IGNORECASE)}
                if not explicitly_requested and dates and not (dates & row_dates) and not is_change_log:
                    continue
                if not explicitly_requested and classes and not (classes & row_classes):
                    paired = (({"L3A", "L3B"} <= classes and "L3AB" in row_classes) or
                              ({"L2A", "L2B"} <= classes and "L2AB" in row_classes))
                    if not paired:
                        continue
                if not explicitly_requested and sessions and not (sessions & row_sessions):
                    continue
                if not explicitly_requested and not (dates or classes or sessions) and not sheet_mentioned:
                    continue

                compact = []
                seen = set()
                for cell in cells:
                    anchor = cell.get("source_cell") or cell.get("coordinate")
                    value = cell.get("value")
                    if value is None or anchor in seen:
                        continue
                    seen.add(anchor)
                    compact.append({"cell": anchor, "value": str(value)[:400]})
                paired = (({"L3A", "L3B"} <= classes and "L3AB" in row_classes) or
                          ({"L2A", "L2B"} <= classes and "L2AB" in row_classes))
                score = (100 if sheet_mentioned else 0) + (20 if filename in mentioned_files else 0)
                score += 10 if dates and dates & row_dates else 0
                score += 6 if classes and (classes & row_classes or paired) else 0
                score += 6 if sessions and sessions & row_sessions else 0
                score += 3 if sheet_folded.startswith("khoa 9") else 0
                evidence.append((score, {"file": "data/" + filename, "sheet": sheet_name,
                                        "row": row_number, "cells": compact}))

    evidence.sort(key=lambda item: item[0], reverse=True)
    evidence = [item[1] for item in evidence[:20]]
    return {"evidence": evidence, "errors": errors,
            "notice": "Không tìm thấy dòng khớp; không suy đoán." if not evidence else ""}


@tool
def read_excel_sources(paths: list) -> dict:
    """Đọc nhiều nguồn Excel A5.
    Input: danh sách đường dẫn .xlsx/.xlsm. Output: files, errors, summary,
    giữ tên file, sheet, dòng và ô nguồn. Chỉ đọc file local; không tác động ra ngoài.
    """
    from excel_reader import read_excel_files
    return read_excel_files(paths)

