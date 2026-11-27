"""Chuẩn hoá và trích xuất lịch đào tạo từ nhiều file Excel, giữ nguyên provenance từng ô.

Tái sử dụng duy nhất `codebase.excel_reader.read_excel_files` để đọc workbook; không tạo luồng đọc thứ hai.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .excel_reader import read_excel_files
from .file_safety import UploadLimits, classify_cell_sensitivity

STANDARD_SCHEDULE_FIELDS = (
    "date",
    "class_name",
    "session_type",
    "session_number",
    "start_time",
    "end_time",
    "topic",
    "room",
    "instructor",
    "room_status",
)

HEADER_SYNONYM_MAP = {
    "ngày": "date",
    "ngay": "date",
    "date": "date",
    "ngay_hoc": "date",
    "lớp": "class_name",
    "lop": "class_name",
    "class": "class_name",
    "class_name": "class_name",
    "session": "session_type",
    "buổi": "session_type",
    "buoi": "session_type",
    "loại buổi": "session_type",
    "chuyên đề": "topic",
    "chuyen de": "topic",
    "topic": "topic",
    "môn học": "topic",
    "phòng": "room",
    "phong": "room",
    "room": "room",
    "giảng viên": "instructor",
    "giang vien": "instructor",
    "gv": "instructor",
    "instructor": "instructor",
    "lecturer": "instructor",
    "giờ bắt đầu": "start_time",
    "start_time": "start_time",
    "giờ kết thúc": "end_time",
    "end_time": "end_time",
}


def _col_letter(coord: str) -> str:
    m = re.match(r"([A-Z]+)", coord or "")
    return m.group(1) if m else ""


def _col_index(coord: str) -> int:
    letters = _col_letter(coord)
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def parse_vn_date(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    m_iso = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", s)
    if m_iso:
        return f"{int(m_iso.group(1)):04d}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"
    m_vn = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", s)
    if m_vn:
        return f"{int(m_vn.group(3)):04d}-{int(m_vn.group(2)):02d}-{int(m_vn.group(1)):02d}"
    return ""


def parse_time_range(text: str, shift_text: str = "") -> tuple[str, str, bool]:
    """Trích (start_time, end_time, is_custom_time) ưu tiên giờ riêng trong ô buổi."""
    m = re.search(r"(\d{1,2})[:h](\d{2})\s*[–\-~]\s*(\d{1,2})[:h](\d{2})", text or "")
    if m:
        return (
            f"{int(m.group(1)):02d}:{int(m.group(2)):02d}",
            f"{int(m.group(3)):02d}:{int(m.group(4)):02d}",
            True,
        )
    low = (shift_text or "").lower()
    if "sáng" in low or "sang" in low:
        return "09:00", "13:00", False
    if "tối" in low or "toi" in low:
        return "18:00", "21:00", False
    return "14:00", "18:00", False


def expand_class_tokens(token: str) -> list[str]:
    clean = (token or "").upper().replace(" ", "")
    if clean in ("L3AB", "L3A+B", "L3A+L3B"):
        return ["L3A", "L3B"]
    if clean in ("L2AB", "L2A+B", "L2A+L2B"):
        return ["L2A", "L2B"]
    return [clean] if clean else []


def parse_rooms_from_lines(lines: list[str], default_room: str = "") -> tuple[list[str], list[str], str]:
    """Trả về (rooms, extra_rooms, room_status)."""
    joined = "\n".join(lines)
    if re.search(r"\bonline\b", joined, re.IGNORECASE):
        return ["Online"], [], "online"

    rooms: list[str] = []
    extra_rooms: list[str] = []
    status = "confirmed"

    for ln in lines:
        low = ln.lower().strip()
        if "chờ xác nhận" in low or "cho xac nhan" in low:
            status = "tentative" if "dự kiến" in low or "du kien" in low else "pending"
        if low.startswith(("phòng thêm:", "phong them:")):
            part = ln.split(":", 1)[1]
            extra_rooms.extend(re.findall(r"\b[A-Z]\d{3}\b", part.upper()))
        elif low.startswith(("phòng dự kiến:", "phong du kien:", "dk:")):
            status = "tentative"
            part = ln.split(":", 1)[1]
            rooms.extend(re.findall(r"\b[A-Z]\d{3}\b", part.upper()))
        elif low.startswith(("phòng:", "phong:")):
            part = ln.split(":", 1)[1]
            found = re.findall(r"\b[A-Z]\d{3}\b", part.upper())
            rooms.extend(found)
            if not found and ("chờ" in low or "cho" in low):
                status = "pending"

    if not rooms and status not in ("pending", "online") and default_room:
        rooms = [default_room]

    return list(dict.fromkeys(rooms)), list(dict.fromkeys(extra_rooms)), status


def extract_workbook_bundle(
    upload_records: list[dict[str, Any]],
    limits: UploadLimits | None = None,
) -> dict[str, Any]:
    """Đọc các workbook đã lưu an toàn qua `excel_reader.read_excel_files` và trích xuất dữ liệu có provenance.

    `upload_records` mỗi phần tử có:
        upload_id (int|str), original_name (str), stored_path (str|Path), uploaded_at (str)
    """
    limits = limits or UploadLimits()
    if not upload_records:
        return {
            "files": [],
            "errors": [],
            "extracted_cells": [],
            "mapping_candidates": [],
            "schedule_items": [],
            "staff_aliases": {},
            "canonical_staff": set(),
            "swap_requests": [],
            "room_capacities": {},
            "learners_count": 0,
            "learners_has_class_mapping": False,
            "source_conflicts": [],
            "pii_summary": {"total_sensitive_cells": 0, "by_flag": {}},
        }

    path_list = [Path(rec["stored_path"]) for rec in upload_records]
    raw = read_excel_files(path_list)

    # Kiểm tra giới hạn số sheet, dòng, cột trên kết quả đọc
    limit_errors = list(raw.get("errors", []))
    valid_files: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for f_obj, rec in zip(raw.get("files", []), upload_records):
        sheets = f_obj.get("sheets", [])
        if len(sheets) > limits.max_sheets:
            limit_errors.append({
                "file": rec["original_name"],
                "error": f"Số sheet ({len(sheets)}) vượt giới hạn cho phép ({limits.max_sheets}).",
            })
            continue
        exceeded = False
        for sh in sheets:
            rows = sh.get("rows", [])
            max_row_num = max((r["row_number"] for r in rows), default=0)
            max_col_num = max((_col_index(c["coordinate"]) for r in rows for c in r.get("cells", [])), default=0)
            if max_row_num > limits.max_rows or max_col_num > limits.max_cols:
                limit_errors.append({
                    "file": rec["original_name"],
                    "error": f"Sheet '{sh['name']}' vượt giới hạn kích thước ({max_row_num}x{max_col_num} > {limits.max_rows}x{limits.max_cols}).",
                })
                exceeded = True
                break
        if not exceeded:
            valid_files.append((f_obj, rec))

    extracted_cells: list[dict[str, Any]] = []
    pii_counts: dict[str, int] = {}
    staff_aliases: dict[str, str] = {}
    canonical_staff: set[str] = set()
    swap_requests: list[dict[str, Any]] = []
    room_capacities: dict[str, int] = {}
    learners_count = 0
    learners_has_class_mapping = False
    mapping_candidates: list[dict[str, Any]] = []

    # Lưu vết từ các sheet nguồn khác nhau để đối chiếu chéo (vd bản chính vs bản chép vs lịch lab)
    schedule_snapshots: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    lab_coach_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    draft_items: list[dict[str, Any]] = []

    # Pass 1: Trích toàn bộ source_cells, danh mục Nhan_su, Đổi buổi, Learners, Lịch lab & mapping mơ hồ
    for f_obj, rec in valid_files:
        wb_name = rec["original_name"]
        upload_id = rec["upload_id"]
        uploaded_at = rec["uploaded_at"]

        for sh in f_obj.get("sheets", []):
            sname = sh["name"]
            rows = sh.get("rows", [])
            headers_by_col: dict[str, str] = {}
            if rows:
                for c in rows[0].get("cells", []):
                    headers_by_col[_col_letter(c["coordinate"])] = str(c.get("value") or "")

            for r in rows:
                for c in r.get("cells", []):
                    col = _col_letter(c["coordinate"])
                    h_hint = headers_by_col.get(col, "")
                    s_flag = classify_cell_sensitivity(sname, h_hint, c.get("value"))
                    if s_flag != "normal":
                        for fl in s_flag.split(","):
                            pii_counts[fl] = pii_counts.get(fl, 0) + 1
                    cell_loc = str(c["coordinate"])
                    if c.get("inherited") and c.get("source_cell") and c["source_cell"] != cell_loc:
                        cell_loc = f"{cell_loc} (gộp {c['source_cell']})"
                    extracted_cells.append({
                        "upload_id": upload_id,
                        "workbook": wb_name,
                        "sheet": sname,
                        "cell_range": cell_loc[:40],
                        "raw_value": "" if c.get("value") is None else str(c.get("value")),
                        "normalized_value": str(c.get("value") or "").strip(),
                        "sensitivity_flag": s_flag,
                    })

            # Nhan_su
            if sname == "Nhan_su" and len(rows) > 1:
                for r in rows[1:]:
                    cmap = {_col_letter(c["coordinate"]): str(c.get("value") or "").strip() for c in r.get("cells", [])}
                    reg = cmap.get("A", "")
                    std = cmap.get("B", "") or reg
                    if reg and std:
                        staff_aliases[reg] = std
                        staff_aliases[std] = std
                        canonical_staff.add(std)

            # Đổi buổi (form)
            elif "đổi buổi" in sname.lower() and len(rows) > 1:
                for r in rows[1:]:
                    cmap = {_col_letter(c["coordinate"]): str(c.get("value") or "").strip() for c in r.get("cells", [])}
                    if not cmap.get("B"):
                        continue
                    swap_requests.append({
                        "coach": staff_aliases.get(cmap.get("B", ""), cmap.get("B", "")),
                        "current_session": cmap.get("D", ""),
                        "target": cmap.get("E", ""),
                        "processed": cmap.get("G", ""),
                        "note": cmap.get("H", ""),
                        "provenance": {
                            "file": wb_name,
                            "sheet": sname,
                            "cell_range": f"B{r['row_number']}:H{r['row_number']}",
                            "upload_id": upload_id,
                            "uploaded_at": uploaded_at,
                        },
                    })

            # Learners
            elif sname.lower() == "learners" or ("learner" in wb_name.lower() and rows):
                hdr = {_col_letter(c["coordinate"]): str(c.get("value") or "").strip().lower() for c in rows[0].get("cells", [])}
                if any(v in ("class", "class_name", "lớp", "lop") for v in hdr.values()):
                    learners_has_class_mapping = True
                learners_count += max(0, len(rows) - 1)

            # Lịch lab 1504-2404 / 2604-0805
            elif sname.lower().startswith("lịch lab"):
                cur_date = ""
                for r in rows:
                    cmap = {_col_letter(c["coordinate"]): c for c in r.get("cells", [])}
                    d_a = parse_vn_date(cmap.get("A", {}).get("value"))
                    if d_a:
                        cur_date = d_a
                        continue
                    d_iso = parse_vn_date(cmap.get("K", {}).get("value")) or cur_date
                    cls = str(cmap.get("B", cmap.get("L", {})).get("value") or "").strip().upper()
                    sess = str(cmap.get("C", cmap.get("M", {})).get("value") or "").strip().upper()
                    if not (d_iso and cls and re.match(r"^(LEC|LAB)\s*\d+", sess)):
                        continue
                    sess_norm = re.sub(r"\s+", " ", sess)
                    coach = str(cmap.get("D", {}).get("value") or "").strip()
                    key_coach = str(cmap.get("E", cmap.get("P", {})).get("value") or "").strip()
                    rooms_raw = str(cmap.get("F", cmap.get("N", {})).get("value") or "").strip()
                    cap_val = cmap.get("H", {}).get("value") if "2604" in sname else cmap.get("G", {}).get("value")

                    key = (d_iso, cls, sess_norm)
                    entry = lab_coach_map.setdefault(key, {
                        "key_coach": "",
                        "lab_coaches": [],
                        "rooms_raw": "",
                        "capacity": None,
                        "provenance": {
                            "file": wb_name,
                            "sheet": sname,
                            "cell_range": f"B{r['row_number']}:P{r['row_number']}",
                            "upload_id": upload_id,
                            "uploaded_at": uploaded_at,
                        },
                    })
                    if key_coach:
                        entry["key_coach"] = key_coach
                    if coach and coach not in entry["lab_coaches"]:
                        entry["lab_coaches"].append(coach)
                    if rooms_raw and not entry["rooms_raw"]:
                        entry["rooms_raw"] = rooms_raw
                    if isinstance(cap_val, (int, float)) and not entry["capacity"]:
                        entry["capacity"] = int(cap_val)

            # Bảng dạng cột tự do / tuỳ biến (không thuộc các sheet chuẩn khoá) -> tạo MappingCandidate
            elif sname not in (
                "Khoá 9 (GĐ1)", "Lịch lớp K9 (bản chép)", "Tong_hop", "Canh_bao",
                "Nhan_su", "Dang_ky_chi_tiet", "Lịch sử chỉnh sửa", "Khoá 8 (GĐ2)",
                "Master Plan", "Workload - Lab coach",
            ) and rows:
                for col, hdr_val in headers_by_col.items():
                    low_h = hdr_val.strip().lower()
                    if not low_h:
                        continue
                    sample = ""
                    for r2 in rows[1:4]:
                        for c2 in r2.get("cells", []):
                            if _col_letter(c2["coordinate"]) == col and c2.get("value") is not None:
                                sample = str(c2["value"])[:120]
                                break
                        if sample:
                            break
                    mapped = HEADER_SYNONYM_MAP.get(low_h)
                    mapping_candidates.append({
                        "upload_id": upload_id,
                        "source_column_or_cell": f"{wb_name} :: {sname} :: {col}1 ({hdr_val})",
                        "raw_sample": sample,
                        "proposed_field": mapped,
                        "ai_confidence": 0.92 if mapped else 0.35,
                        "ai_rationale": f"Khớp từ điển cột chuẩn '{low_h}'" if mapped else "Tiêu đề cột chưa rõ nghĩa, cần Admin xác nhận hoặc chạy gợi ý AI.",
                        "is_mock": False,
                        "admin_decision": "accepted" if mapped else "needs_confirmation",
                    })

    # Pass 2: Trích xuất buổi học từ Khoá 9 (GĐ1), Lịch lớp K9 (bản chép) và bảng dạng cột đã khớp
    for f_obj, rec in valid_files:
        wb_name = rec["original_name"]
        upload_id = rec["upload_id"]
        uploaded_at = rec["uploaded_at"]

        for sh in f_obj.get("sheets", []):
            sname = sh["name"]
            rows = sh.get("rows", [])
            if sname in ("Khoá 9 (GĐ1)", "Lịch lớp K9 (bản chép)"):
                is_primary_sheet = sname == "Khoá 9 (GĐ1)"
                source_ts = ""
                if rows and rows[0].get("cells"):
                    for c in rows[0]["cells"]:
                        if _col_letter(c["coordinate"]) == "D" and c.get("value"):
                            source_ts = str(c["value"])
                # Đọc tiêu đề mặc định D5 / E5
                col_defaults = {"D": "H209", "E": "H210", "F": "", "G": "", "H": ""}
                for r in rows:
                    if r["row_number"] < 6:
                        continue
                    cmap = {_col_letter(c["coordinate"]): c for c in r.get("cells", [])}
                    d_iso = parse_vn_date(cmap.get("A", {}).get("value"))
                    shift_raw = str(cmap.get("C", {}).get("value") or "")
                    if not d_iso or not shift_raw:
                        continue

                    # Nếu ô D6 gộp toàn bộ chiều ngang (vd KHAI GIẢNG / NGHỈ LỄ), bỏ qua không coi là buổi học thường
                    for col in ("D", "E", "F", "G", "H"):
                        cell = cmap.get(col)
                        if not cell or not cell.get("value"):
                            continue
                        if cell.get("inherited") and _col_letter(cell.get("source_cell")) != col:
                            continue
                        text = str(cell["value"]).strip()
                        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                        if not lines:
                            continue
                        m_head = re.match(
                            r"^(L3AB|L2AB|L2A\+B|L3A|L3B|L2A|L2B)\s*[—\-–]\s*(LEC|LAB)\s*(\d+)",
                            lines[0],
                            re.IGNORECASE,
                        )
                        if not m_head:
                            continue

                        cls_raw = m_head.group(1).upper()
                        sess_type = m_head.group(2).upper()
                        sess_num = int(m_head.group(3))
                        sess_code = f"{sess_type} {sess_num}"
                        start_t, end_t, _ = parse_time_range(text, shift_raw)
                        rooms, extra_rooms, room_status = parse_rooms_from_lines(lines[1:], col_defaults[col])

                        topic = ""
                        instructor = ""
                        for ln in lines[1:]:
                            low_ln = ln.lower()
                            if re.match(r"^(giảng\s*viên|giang\s*vien|gv)\s*:", ln, re.IGNORECASE):
                                instructor = ln.split(":", 1)[1].strip()
                                continue
                            if re.match(r"^\d{1,2}[:h]\d{2}", ln) or low_ln == "online" or low_ln.startswith(("phòng", "phong", "dk:")):
                                continue
                            if not topic:
                                topic = ln

                        # Cờ cảnh báo nếu trong ô có dấu hiệu prompt injection
                        if classify_cell_sensitivity(sname, "", text).startswith("prompt_injection"):
                            mapping_candidates.append({
                                "upload_id": upload_id,
                                "source_column_or_cell": f"{wb_name} :: {sname} :: {cell['coordinate']}",
                                "raw_sample": text[:160],
                                "proposed_field": None,
                                "ai_confidence": 0.1,
                                "ai_rationale": "Ô chứa chuỗi giống chỉ dẫn hệ thống; giữ là dữ liệu thô, cần Admin kiểm tra.",
                                "is_mock": False,
                                "admin_decision": "needs_confirmation",
                            })

                        snap_key = (d_iso, cls_raw, sess_type, sess_num)
                        snap = {
                            "date": d_iso,
                            "class_name": cls_raw,
                            "classes": expand_class_tokens(cls_raw),
                            "session_type": sess_type,
                            "session_number": sess_num,
                            "start_time": start_t,
                            "end_time": end_t,
                            "topic": topic or sess_code,
                            "rooms": rooms + extra_rooms,
                            "room": ", ".join(rooms + extra_rooms),
                            "room_status": room_status,
                            "instructor": instructor,
                            "provenance": {
                                "file": wb_name,
                                "sheet": sname,
                                "cell_range": cell["source_cell"] if cell.get("inherited") else cell["coordinate"],
                                "source_cell": cell["coordinate"],
                                "upload_id": upload_id,
                                "uploaded_at": uploaded_at,
                                "source_timestamp": source_ts,
                                "is_primary_sheet": is_primary_sheet,
                            },
                        }
                        schedule_snapshots.setdefault(snap_key, []).append(snap)

            # Bảng Excel dạng cột chuẩn hoá (vd file lịch tự dựng có header Ngày, Lớp, Buổi, Phòng...)
            elif sname not in (
                "Tong_hop", "Canh_bao", "Nhan_su", "Dang_ky_chi_tiet",
                "Lịch sử chỉnh sửa", "Khoá 8 (GĐ2)", "Master Plan", "Workload - Lab coach",
                "Đổi buổi (form)", "Learners",
            ) and not sname.lower().startswith("lịch lab") and len(rows) > 1:
                hdr_map = {
                    _col_letter(c["coordinate"]): HEADER_SYNONYM_MAP.get(str(c.get("value") or "").strip().lower(), "")
                    for c in rows[0].get("cells", [])
                }
                if {"date", "class_name"}.issubset(set(hdr_map.values())):
                    for r in rows[1:]:
                        by_field: dict[str, str] = {}
                        coords: list[str] = []
                        for c in r.get("cells", []):
                            fld = hdr_map.get(_col_letter(c["coordinate"]), "")
                            if fld and c.get("value") is not None:
                                by_field[fld] = str(c["value"]).strip()
                                coords.append(c["coordinate"])
                        d_iso = parse_vn_date(by_field.get("date"))
                        cls_raw = by_field.get("class_name", "").upper()
                        if not d_iso or not cls_raw:
                            continue
                        sess_txt = by_field.get("session_type", "LAB 1").upper()
                        m_s = re.search(r"(LEC|LAB)\s*(\d+)", sess_txt)
                        s_type = m_s.group(1) if m_s else ("LEC" if "LEC" in sess_txt else "LAB")
                        s_num = int(m_s.group(2)) if m_s else 1
                        st = by_field.get("start_time") or "09:00"
                        et = by_field.get("end_time") or "13:00"
                        rm_txt = by_field.get("room", "")
                        rm_status = "pending" if ("chờ" in rm_txt.lower() or not rm_txt) else (
                            "tentative" if ("dk:" in rm_txt.lower() or "dự kiến" in rm_txt.lower()) else (
                                "online" if "online" in rm_txt.lower() else "confirmed"
                            )
                        )
                        rm_codes = ["Online"] if rm_status == "online" else re.findall(r"\b[A-Z]\d{3}\b", rm_txt.upper())
                        snap_key = (d_iso, cls_raw, s_type, s_num)
                        schedule_snapshots.setdefault(snap_key, []).append({
                            "date": d_iso,
                            "class_name": cls_raw,
                            "classes": expand_class_tokens(cls_raw),
                            "session_type": s_type,
                            "session_number": s_num,
                            "start_time": st,
                            "end_time": et,
                            "topic": by_field.get("topic") or f"{s_type} {s_num}",
                            "rooms": rm_codes,
                            "room": ", ".join(rm_codes) if rm_codes else rm_txt,
                            "room_status": rm_status,
                            "instructor": by_field.get("instructor", ""),
                            "provenance": {
                                "file": wb_name,
                                "sheet": sname,
                                "cell_range": f"{coords[0]}:{coords[-1]}" if coords else f"row {r['row_number']}",
                                "source_cell": coords[0] if coords else f"row {r['row_number']}",
                                "upload_id": upload_id,
                                "uploaded_at": uploaded_at,
                                "source_timestamp": "",
                                "is_primary_sheet": True,
                            },
                        })

    # Pass 3: Tổng hợp các snapshot thành `schedule_items` + phát hiện mâu thuẫn giữa các nguồn
    source_conflicts: list[dict[str, Any]] = []
    for snap_key, snaps in sorted(schedule_snapshots.items()):
        d_iso, cls_raw, s_type, s_num = snap_key
        # Ưu tiên bản chính Khoá 9 (GĐ1), ghép nhiều phòng song song (vd D & E) nếu cùng sheet
        primary_snaps = [s for s in snaps if s["provenance"].get("is_primary_sheet")] or snaps
        secondary_snaps = [s for s in snaps if not s["provenance"].get("is_primary_sheet")]

        merged_rooms: list[str] = []
        merged_instructors: list[str] = []
        provenances: list[dict[str, Any]] = []
        room_statuses: set[str] = set()
        for sp in primary_snaps:
            for r in sp["rooms"]:
                if r not in merged_rooms:
                    merged_rooms.append(r)
            if sp["instructor"] and sp["instructor"] not in merged_instructors:
                merged_instructors.append(sp["instructor"])
            room_statuses.add(sp["room_status"])
            provenances.append(sp["provenance"])

        final_room_status = "pending" if "pending" in room_statuses else (
            "tentative" if "tentative" in room_statuses else (
                "online" if "online" in room_statuses else "confirmed"
            )
        )

        # Kiểm tra mâu thuẫn với bản chép (Lịch lớp K9 (bản chép)) hoặc Lịch lab
        if secondary_snaps:
            sec = secondary_snaps[0]
            if sorted(sec["rooms"]) != sorted(merged_rooms) or sec["room_status"] != final_room_status:
                source_conflicts.append({
                    "session_key": f"{cls_raw} {s_type} {s_num} ({d_iso})",
                    "primary_rooms": merged_rooms,
                    "primary_status": final_room_status,
                    "primary_ts": primary_snaps[0]["provenance"].get("source_timestamp", ""),
                    "primary_prov": primary_snaps[0]["provenance"],
                    "secondary_rooms": sec["rooms"],
                    "secondary_status": sec["room_status"],
                    "secondary_ts": sec["provenance"].get("source_timestamp", ""),
                    "secondary_prov": sec["provenance"],
                })

        # Ghép lab coach & key coach theo đúng (date, class, session)
        sess_code = f"{s_type} {s_num}"
        lab_info = lab_coach_map.get((d_iso, cls_raw, sess_code)) or {}
        assistants = list(lab_info.get("lab_coaches", []))
        if lab_info.get("key_coach"):
            assistants = [f"Key: {lab_info['key_coach']}"] + assistants
        if lab_info.get("provenance"):
            provenances.append(lab_info["provenance"])
            # Kiểm tra lệch trạng thái dự kiến dk: từ bảng Lịch lab
            if "dk:" in lab_info.get("rooms_raw", "").lower() and final_room_status == "confirmed":
                source_conflicts.append({
                    "session_key": f"{cls_raw} {s_type} {s_num} ({d_iso})",
                    "primary_rooms": merged_rooms,
                    "primary_status": final_room_status,
                    "primary_ts": primary_snaps[0]["provenance"].get("source_timestamp", ""),
                    "primary_prov": primary_snaps[0]["provenance"],
                    "secondary_rooms": re.findall(r"\b[A-Z]\d{3}\b", lab_info["rooms_raw"].upper()),
                    "secondary_status": "tentative (dk:)",
                    "secondary_ts": "Lịch lab",
                    "secondary_prov": lab_info["provenance"],
                })

        rep = primary_snaps[0]
        draft_items.append({
            "date": d_iso,
            "class_name": cls_raw,
            "classes": rep["classes"],
            "session_type": s_type,
            "session_number": s_num,
            "start_time": rep["start_time"],
            "end_time": rep["end_time"],
            "topic": rep["topic"],
            "room": ", ".join(merged_rooms) if merged_rooms else ("Online" if final_room_status == "online" else ""),
            "rooms": merged_rooms,
            "instructor": ", ".join(merged_instructors),
            "instructors": merged_instructors,
            "assistants": assistants,
            "room_status": final_room_status,
            "provenance": provenances,
        })

    return {
        "files": [{"original_name": rec["original_name"], "upload_id": rec["upload_id"], "sheets": [s["name"] for s in f["sheets"]]} for f, rec in valid_files],
        "errors": limit_errors,
        "extracted_cells": extracted_cells,
        "mapping_candidates": mapping_candidates,
        "schedule_items": draft_items,
        "staff_aliases": staff_aliases,
        "canonical_staff": canonical_staff,
        "swap_requests": swap_requests,
        "room_capacities": room_capacities,
        "learners_count": learners_count,
        "learners_has_class_mapping": learners_has_class_mapping,
        "source_conflicts": source_conflicts,
        "pii_summary": {"total_sensitive_cells": sum(pii_counts.values()), "by_flag": pii_counts},
    }
