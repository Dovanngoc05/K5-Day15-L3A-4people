"""Canonical workbooks plus a conservative adapter for the three project sources."""
from io import BytesIO
from datetime import datetime
import re

from openpyxl import load_workbook

from .excel import SCHEMA, OPTIONAL_COLUMNS, empty_data, read_tables, text


def import_workbook(payload):
    book = load_workbook(BytesIO(payload), data_only=False, keep_links=False)
    names = set(book.sheetnames)
    book.close()
    canonical = names & set(SCHEMA)
    if not canonical and "Schedule" in names:
        raise ValueError("Đây là file kết quả lịch, không phải đầu vào. Chọn a5-input-demo-hoan-chinh.xlsx hoặc workbook có People, Sessions, Slots, Rooms, Enrollments, Availability, Weights.")
    if canonical:
        parsed=read_tables(BytesIO(payload))
        for name in canonical:
            for row in parsed[name]:
                missing=set(SCHEMA[name])-OPTIONAL_COLUMNS.get(name,set())-row.keys()
                if missing:
                    raise ValueError(name+": thiếu cột "+", ".join(sorted(missing)))
        result={k:parsed[k] for k in SCHEMA if k in canonical}
        if parsed.get("Assumptions"):
            result["_Assumptions"]=parsed["Assumptions"][:200]
        return result, ["Đã đọc workbook chuẩn; các sheet được cung cấp sẽ thay thế bảng cùng tên sau xác nhận."]
    book=load_workbook(BytesIO(payload),data_only=True,keep_links=False)
    try:
        tables={}
        notes=[]
        if "Learners" in names:
            sheet=book["Learners"]
            rows=sheet.iter_rows(values_only=True)
            headers=[text(x) for x in next(rows)]
            people=[]
            for values in rows:
                row=dict(zip(headers,values))
                pid=text(row.get("hv"))
                if pid:
                    people.append(dict(person_id=pid,name=text(row.get("full_name")) or pid,role="student",subjects="",skills="",max_minutes_day="",max_minutes_week=""))
            tables["People"]=people
            notes.append("Learners: chỉ nhập danh tính giả lập; thiếu đăng ký lớp và giờ rảnh. Không tự suy đoán lớp từ mã/ngày tạo.")
        if "Khoá 9 (GĐ1)" in names:
            sheet=book["Khoá 9 (GĐ1)"]
            sessions,slots,people,rooms={},{},{},{}
            current_day=""
            for row in sheet.iter_rows():
                day=text(sheet.cell(row[0].row,1).value)
                if re.fullmatch(r"\d{2}/\d{2}/\d{4}",day):
                    current_day=datetime.strptime(day,"%d/%m/%Y").date().isoformat()
                if not current_day:
                    continue
                period=text(sheet.cell(row[0].row,3).value)
                default_hours=re.search(r"(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})",period)
                for cell in row[3:8]:
                    content=text(cell.value)
                    match=re.search(r"(L[23](?:A\+B|AB|A|B))\s*[—–-]\s*(LEC|LAB)\s*(\d+)",content)
                    if not match:
                        continue
                    cls,kind,num=match.groups()
                    sid=f"{current_day}-{cls}-{kind}{num}"
                    if sid in sessions:
                        continue
                    hours=re.search(r"(?m)^\s*(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})",content) or default_hours
                    if not hours:
                        notes.append(sid+": chưa đọc được giờ; cần bổ sung trong workbook chuẩn.")
                        continue
                    start,end=hours.groups()
                    slot_id=f"{current_day}-{start}-{end}"
                    slots[slot_id]=dict(slot_id=slot_id,date=current_day,start=start,end=end)
                    duration=(datetime.strptime(end,"%H:%M")-datetime.strptime(start,"%H:%M")).seconds//60
                    lecturers=set(re.findall(r"Lecturer\s+[A-Z]+",content))
                    for lecturer in lecturers:
                        people[lecturer]=dict(person_id=lecturer,name=lecturer,role="teacher",subjects="",skills="",max_minutes_day="",max_minutes_week="")
                    room_line=re.search(r"(?m)^Phòng:\s*(.+)$",content)
                    room_ids=re.findall(r"\b[A-Z]\d{3}\b",room_line[1]) if room_line else []
                    for rid in room_ids:
                        rooms[rid]=dict(room_id=rid,capacity="")
                    lines=content.splitlines()
                    subject=next((l.strip() for l in lines[1:] if l.strip() and not re.match(r"Online|Phòng|Giảng|\d{2}:\d{2}",l.strip())),"")
                    sessions[sid]=dict(session_id=sid,class_id=cls,subject=subject,duration_minutes=duration,
                        required_skill="",assistant_count="",key_coach_required="",locked=1,baseline_slot=slot_id,
                        baseline_teacher=next(iter(lecturers)) if len(lecturers)==1 else "",baseline_assistants="",baseline_key_coach="",
                        baseline_room=room_ids[0] if len(room_ids)==1 else "")
                    notes.append(f"{sid}: nguồn Khoá 9 (GĐ1)/{cell.coordinate}; giữ khoá để admin xác nhận. Phòng nhiều/chưa chốt/online và phân công nhiều người cần bổ sung rõ.")
            tables.update(Sessions=list(sessions.values()),Slots=list(slots.values()),People=list(people.values()),Rooms=list(rooms.values()))
        if "Lịch lab 2604-0805" in names:
            found={}
            for sheet_name in ["Lịch lab 1504-2404","Lịch lab 2604-0805"]:
                if sheet_name not in names:
                    continue
                sheet=book[sheet_name]
                for row in sheet.iter_rows():
                    for cell in row:
                        for label in re.findall(r"Lab Coach\s+[A-Z]+",text(cell.value)):
                            found[label]=dict(person_id=label,name=label,role="assistant",subjects="",skills="",max_minutes_day="",max_minutes_week="")
            tables["People"]=list(found.values())
            notes.append("Đã lấy nhãn coach. Vai key coach, kỹ năng, giờ rảnh và phân công cần admin xác nhận; không coi form đăng ký/đổi ca là phân công đã duyệt.")
        if not tables:
            raise ValueError("Không nhận diện được cấu trúc. Dùng workbook mẫu hoặc các sheet nguồn Learners, Khoá 9 (GĐ1), Lịch lab 2604-0805.")
        return tables,notes
    finally:
        book.close()


def combine_import(current, imports):
    """Canonical sheets replace explicitly; raw people/rooms merge by ID, never guess fields."""
    result={k:[dict(r) for r in current.get(k,[])] for k in SCHEMA}
    for tables, canonical in imports:
        for table,rows in tables.items():
            if canonical or table not in {"People","Rooms"}:
                result[table]=rows
            else:
                key="person_id" if table=="People" else "room_id"
                index={r[key]:r for r in result[table]}
                for row in rows:
                    if row[key] not in index:
                        index[row[key]]=row
                result[table]=list(index.values())
    return result
