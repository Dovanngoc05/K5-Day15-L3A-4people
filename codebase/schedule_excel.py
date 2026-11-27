"""Read the three scheduling workbooks and prepare a draft from the original layout."""
from collections import defaultdict
from datetime import datetime, time
from io import BytesIO
from pathlib import Path, PurePosixPath
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook

FILES = ("teaching-schedule.xlsx", "lab-coach-schedule.xlsx", "learners.xlsx")
SCHEMA = {
    "Classes": "class_id subject groups assistants keys locked existing_slot existing_teacher existing_coaches",
    "Slots": "class_id slot_id day start end rooms capacity",
    "Teachers": "person skills daily_minutes weekly_minutes",
    "Coaches": "person role skills daily_minutes weekly_minutes",
    "TeacherAvailability": "person day start end preferred",
    "CoachAvailability": "person day start end preferred",
    "Learners": "student_id full_name group",
    "LearnerAvailability": "person day start end preferred",
}
LIMIT = 8 * 1024 * 1024


def scan(payload):
    """Use ClamAV or Windows Defender and fail closed on any scanner error."""
    configured = os.environ.get("SCHEDULE_CLAMSCAN")
    clam = configured or shutil.which("clamscan")
    defender = None
    if os.name == "nt" and not clam:
        root = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        versions = sorted(root.glob("Microsoft/Windows Defender/Platform/*/MpCmdRun.exe"), reverse=True)
        fallback = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender/MpCmdRun.exe"
        defender = next(iter(versions), fallback)
    if not clam and (not defender or not defender.is_file()):
        raise ValueError("Chưa có trình quét virus. Cần ClamAV hoặc Microsoft Defender.")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "upload.xlsx"
        path.write_bytes(payload)
        command = ([clam, "--no-summary", str(path)] if clam else
                   [str(defender), "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"])
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("Không chạy được trình quét virus.") from error
        if result.returncode != 0:
            raise ValueError("Trình quét phát hiện tệp đáng ngờ hoặc không thể xác nhận an toàn.")


def open_excel(payload, *, uploaded=True):
    if not payload or len(payload) > LIMIT:
        raise ValueError("Tệp Excel phải có dung lượng từ 1 byte đến 8 MB.")
    if uploaded:
        scan(payload)
    try:
        with ZipFile(BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > 500 or sum(m.file_size for m in members) > 32 * 1024 * 1024:
                raise ValueError("Tệp Excel vượt giới hạn giải nén.")
            paths = [m.filename.casefold() for m in members]
            if len(set(paths)) != len(paths):
                raise ValueError("Tệp Excel có thành phần trùng tên.")
            if any(PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts
                   or "\\" in p or any(x in p for x in ("vbaproject", "externallinks/", "embeddings/", "activex/", "macrosheets/"))
                   for p in paths):
                raise ValueError("Tệp chứa đường dẫn hoặc thành phần Excel không được hỗ trợ.")
        book = load_workbook(BytesIO(payload), read_only=True, keep_links=False)
        for sheet in book:
            if (sheet.max_row or 0) > 20000 or (sheet.max_column or 0) > 100:
                book.close()
                raise ValueError("Sheet vượt giới hạn số dòng hoặc cột.")
        return book
    except (BadZipFile, KeyError, OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"Excel không hợp lệ. {error}") from error
    except Exception as error:
        raise ValueError("Không đọc được cấu trúc Excel.") from error


def clean(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    if len(text) > 500 or any(unicodedata.category(c).startswith("C") for c in text):
        raise ValueError("Ô chứa ký tự điều khiển hoặc vượt 500 ký tự.")
    return text


def split(value):
    return tuple(dict.fromkeys(part.strip() for part in value.split(";") if part.strip()))


def rows(book, name):
    if name not in book:
        raise ValueError(f"Thiếu sheet {name}.")
    sheet = book[name]
    cells = sheet.iter_rows()
    header = [clean(cell.value) for cell in next(cells, ())]
    required = SCHEMA[name].split()
    if any(header.count(key) != 1 for key in required):
        raise ValueError(f"Sheet {name} cần các cột {', '.join(required)}.")
    indices = {key: header.index(key) for key in required}
    for number, row in enumerate(cells, 2):
        try:
            if not any(cell.value is not None for cell in row):
                continue
            if any(cell.data_type in {"f", "e"} for cell in row):
                raise ValueError("Hãy thay công thức hoặc ô lỗi bằng giá trị.")
            yield number, {key: clean(row[index].value) for key, index in indices.items()}
        except ValueError as error:
            raise ValueError(f"{name}, dòng {number}. {error}") from error


def day_value(value):
    value = value.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Ngày không hợp lệ ({value}). Dùng YYYY-MM-DD.")


def minutes(value):
    try:
        clock = time.fromisoformat(value)
        if clock.second or clock.microsecond or clock.tzinfo:
            raise ValueError
        return clock.hour * 60 + clock.minute
    except ValueError as error:
        raise ValueError(f"Giờ không hợp lệ ({value}). Dùng HH:MM.") from error


def write_book(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, header, data in sheets:
        sheet = book.create_sheet(name)
        sheet.append(header)
        for row_number, row in enumerate(data, 2):
            sheet.append(row)
            for column, value in enumerate(row, 1):
                if isinstance(value, str) and value.startswith(("=", "#")):
                    sheet.cell(row_number, column).data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    target = BytesIO()
    book.save(target)
    return target.getvalue()


def draft(books):
    """Extract candidate sessions and source hints without assuming missing facts."""
    teaching, coaching, learners = books
    if "Khoá 9 (GĐ1)" not in teaching or "Learners" not in learners:
        raise ValueError("Thiếu sheet lịch gốc hoặc danh sách Learners.")
    ranges = r"(\d{2}:\d{2})\s*[-–—]\s*(\d{2}:\d{2})"
    coach_hints = defaultdict(list)
    coach_roles = defaultdict(set)
    for sheet_name, shift_column in (("Lịch lab 1504-2404", 5), ("Lịch lab 2604-0805", 6)):
        if sheet_name not in coaching:
            raise ValueError(f"Thiếu sheet {sheet_name}.")
        day = group = session = shift = None
        for row in coaching[sheet_name].values:
            label = str(row[0] or "")
            match = re.search(r"\d{2}/\d{2}/\d{4}", label)
            if match:
                day = day_value(match[0])
                group = session = shift = None
            if not day or label == "STT":
                continue
            if row[1] and row[2]:
                group, session = str(row[1]).strip(), str(row[2]).strip()
                shift = None
            shift = row[shift_column] or shift
            if not group or not session or not shift:
                continue
            for role, cell in (("lab", row[3]), ("key", row[4])):
                for person in re.findall(r"Lab Coach [A-Z]+\b", str(cell or "")):
                    coach_roles[person].add(role)
                    coach_hints[day, str(shift).strip(), group, session.casefold()].append((role, person))
    classes, slots, hints = [], [], []
    teacher_hints = set()
    current_day = None
    for number, row in enumerate(teaching["Khoá 9 (GĐ1)"].values, 1):
        if number < 6:
            continue
        if row[0]:
            current_day = day_value(str(row[0]))
        timing = re.search(ranges, str(row[2] or ""))
        if not timing or not current_day:
            continue
        for col, cell in enumerate(row[3:8], 4):
            if not cell:
                continue
            lines = str(cell).splitlines()
            label = lines[0]
            match = re.match(r"(L[23](?:AB|A|B))\s*[—–-]\s*(.+)", label)
            opening = label == "KHAI GIẢNG KHOÁ 9"
            if not match and not opening:
                continue
            group, session = match.groups() if match else ("", label)
            groups = ";".join((group[:2]+"A", group[:2]+"B")) if group.endswith("AB") else group
            topic = next((line for line in lines[1:] if ":" not in line[:12] and not re.fullmatch(ranges, line)), label)
            actual = re.search(ranges, "\n".join(lines[1:])) or timing
            room_line = next((line.partition(":")[2].strip() for line in lines if line.startswith("Phòng:")), "")
            teachers = re.findall(r"Lecturer [A-Z]+\b", str(cell))
            teacher_hints.update(teachers)
            shift = str(row[2]).split(" (")[0]
            coaches = coach_hints[current_day, shift, group, session.casefold()]
            class_id = f"K9-R{number}C{col}"
            slot_id = class_id + "-1"
            # Split lecture columns in the source may require new group names.
            classes.append((class_id, topic, groups, None, None, 0, slot_id,
                            teachers[0] if len(teachers) == 1 else None,
                            ";".join(sorted({person for _, person in coaches}))))
            slots.append((class_id, slot_id, current_day.isoformat(), *actual.groups(),
                          room_line.replace(", ", ";"), None))
            hints.append((class_id, label, " | ".join(lines), str(row[2]),
                          "; ".join(sorted({f"{role}: {person}" for role, person in coaches}))))
    original = iter(learners["Learners"].values)
    columns = list(next(original, ()))
    if "student_id" not in columns or "full_name" not in columns:
        raise ValueError("Learners cần student_id và full_name.")
    ident, name = columns.index("student_id"), columns.index("full_name")
    students = [(clean(row[ident]), clean(row[name]), None)
                for row in original if row[ident] is not None]

    def sheet(name, data=()):
        return name, SCHEMA[name].split(), data

    return (
        write_book([sheet("Classes", classes), sheet("Slots", slots),
                    sheet("Teachers", [(p, None, None, None) for p in sorted(teacher_hints)]),
                    sheet("TeacherAvailability"),
                    ("SourceHints", ["class_id", "session", "source", "shift", "coaches"], hints)]),
        write_book([sheet("Coaches", [(p, ";".join(sorted(r)), None, None, None)
                                      for p, r in sorted(coach_roles.items())]), sheet("CoachAvailability")]),
        write_book([sheet("Learners", students), sheet("LearnerAvailability")]),
    )
