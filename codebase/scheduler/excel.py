"""Excel persistence and explicit canonical input schema; no SQL dependency."""
from datetime import datetime, date, time
from io import BytesIO
from pathlib import Path
import os
import tempfile

from openpyxl import Workbook, load_workbook

SCHEMA = {
    "People": ["person_id", "name", "role", "subjects", "skills", "max_minutes_day", "max_minutes_week", "student_id"],
    "Sessions": ["session_id", "class_id", "subject", "duration_minutes", "required_skill", "assistant_count", "key_coach_required", "locked", "baseline_slot", "baseline_teacher", "baseline_assistants", "baseline_key_coach", "baseline_room", "allowed_slots", "allowed_rooms"],
    "Slots": ["slot_id", "date", "start", "end"],
    "Rooms": ["room_id", "capacity"],
    "Enrollments": ["person_id", "class_id"],
    "Availability": ["person_id", "slot_id", "available", "preferred"],
    "Weights": ["constraint_id", "weight"],
}
DEFAULT_WEIGHTS = dict(zip([f"SC-{i:02}" for i in range(1, 8)], [100, 30, 20, 20, 15, 10, 5]))
OPTIONAL_COLUMNS = {"People": {"student_id"}, "Sessions": {"allowed_slots", "allowed_rooms"}}


def text(value):
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value).strip()


def split(value):
    return {v.strip() for v in text(value).split("|") if v.strip()}


def workbook_bytes(tables, schema=None):
    book = Workbook()
    book.remove(book.active)
    for name, rows in tables.items():
        sheet = book.create_sheet(name)
        headers = (schema or {}).get(name) or list(dict.fromkeys(k for row in rows for k in row)) or ["empty"]
        sheet.append(headers)
        for row_number,row in enumerate(rows,start=2):
            values=[row.get(key, "") for key in headers]
            sheet.append(values)
            # All user text is literal text, never an executable Excel formula.
            for column,value in enumerate(values,start=1):
                if isinstance(value, str):
                    sheet.cell(row_number,column).data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(44, max(18, len(str(col[0].value)) + 3))
    if not tables:
        book.create_sheet("Empty")
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def read_tables(source, *, sheets=None):
    book = load_workbook(source, data_only=False, keep_links=False, read_only=sheets is not None)
    try:
        result = {}
        for sheet in book:
            if sheets is not None and sheet.title not in sheets:
                continue
            if sheet.max_row * sheet.max_column > 500_000:
                raise ValueError("Sheet quá lớn: " + sheet.title)
            iterator = sheet.iter_rows()
            first = next(iterator, ())
            headers = [text(c.value) for c in first]
            if len([h for h in headers if h]) != len(set(h for h in headers if h)):
                raise ValueError("Tên cột trùng: " + sheet.title)
            rows = []
            for row in iterator:
                if any(c.data_type == "f" for c in row):
                    raise ValueError("Hãy thay công thức bằng giá trị trong sheet " + sheet.title)
                values = {}
                for key,cell in zip(headers,row):
                    if not key:
                        continue
                    value=cell.value
                    if sheet.title=="Slots" and key=="date" and isinstance(value,datetime):
                        value=value.date().isoformat()
                    if sheet.title=="Slots" and key in {"start","end"} and isinstance(value,(datetime,time)):
                        if value.second or value.microsecond:
                            raise ValueError("Khung giờ cần chính xác đến phút, không có giây.")
                        value=value.strftime("%H:%M")
                    if key in {"available","preferred","locked","key_coach_required"} and isinstance(value,bool):
                        value=int(value)
                    values[key]=text(value)
                if any(values.values()):
                    rows.append(values)
            result[sheet.title] = rows
        return result
    finally:
        book.close()


def atomic_write(path, tables, schema=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = workbook_bytes(tables, schema)
    fd, temporary = tempfile.mkstemp(prefix=".excel-", suffix=".xlsx", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def empty_data():
    result = {key: [] for key in SCHEMA}
    result["Weights"] = [{"constraint_id": k, "weight": v} for k, v in DEFAULT_WEIGHTS.items()]
    return result
