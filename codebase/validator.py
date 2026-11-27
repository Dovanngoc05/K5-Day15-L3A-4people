"""Bộ kiểm tra ràng buộc xác định bằng code thuần (KHÔNG dùng LLM).

Thực thi:
  - Hard Constraints (chặn công bố nếu còn lỗi `blocking`):
      HC-REQ: Đủ trường bắt buộc và khung giờ hợp lệ (start_time < end_time).
      HC-01: Giảng viên không dạy hai buổi chồng giờ cùng lúc.
      HC-02: Lớp/học viên không tham gia hai buổi chồng giờ cùng lúc (tách đúng L3AB = L3A+L3B, L2AB = L2A+L2B).
      HC-03: Trợ giảng / Lab Coach / Key Coach không hỗ trợ hai buổi chồng giờ cùng lúc.
      HC-09: Mọi buổi học phải có giảng viên.
      HC-11: Hai buổi offline độc lập không được trùng phòng vật lý trong cùng khoảng giờ.
      HC-ROOM-STATUS: Buổi offline không được ở trạng thái phòng `pending` (chờ xác nhận) hoặc `tentative` (dự kiến/dk:) khi công bố.
      HC-SOURCE-CONFLICT: Phát hiện mâu thuẫn phòng/trạng thái giữa bản chính và bản chép/lịch lab.
      HC-MAPPING-PENDING: Còn đề xuất mapping chưa được Admin xác nhận.
  - Soft / Readiness Warnings (`warning`, không tự suy đoán hay tự sửa):
      HC-07-DATA: Thiếu ánh xạ học viên-lớp-phòng (vd learners.xlsx chỉ có 5 cột) -> báo thiếu dữ liệu kiểm sức chứa.
      HC-INJECTION-CELL: Ô dữ liệu chứa chuỗi giống lệnh điều khiển AI -> giữ nguyên là dữ liệu, cảnh báo Admin.
      SC-SWAP-UNSYNCED: Form đổi ca chưa xử lý / chưa cập nhật sheet.
      SC-STAFF-ALIAS: Tên nhân sự lệch danh mục chuẩn Nhan_su.
"""
from __future__ import annotations

import json
import re
from typing import Any

RULESET_VERSION = "a5-ruleset-1.0"


def _to_minutes(hhmm: str) -> int:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", hhmm or "")
    if not m:
        return -1
    return int(m.group(1)) * 60 + int(m.group(2))


def _intervals_overlap(s1: int, e1: int, s2: int, e2: int) -> bool:
    if s1 < 0 or e1 < 0 or s2 < 0 or e2 < 0:
        return False
    return s1 < e2 and s2 < e1


def _expand_classes(cls_name: str) -> set[str]:
    clean = (cls_name or "").upper().replace(" ", "")
    if clean in ("L3AB", "L3A+B", "L3A+L3B"):
        return {"L3A", "L3B"}
    if clean in ("L2AB", "L2A+B", "L2A+L2B"):
        return {"L2A", "L2B"}
    return {clean} if clean else set()


def _split_csv_list(val: str) -> list[str]:
    if not val:
        return []
    return [x.strip() for x in re.split(r"[,;]+", val) if x.strip()]


def run_deterministic_validation(
    items: list[dict[str, Any]],
    *,
    pending_mappings: list[dict[str, Any]] | None = None,
    source_conflicts: list[dict[str, Any]] | None = None,
    swap_requests: list[dict[str, Any]] | None = None,
    canonical_staff: set[str] | None = None,
    learners_count: int = 0,
    learners_has_class_mapping: bool = False,
    sensitive_cells: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Chạy toàn bộ kiểm tra ràng buộc xác định trên danh sách schedule_items của một phiên bản."""
    issues: list[dict[str, Any]] = []
    pending_mappings = pending_mappings or []
    source_conflicts = source_conflicts or []
    swap_requests = swap_requests or []
    canonical_staff = canonical_staff or set()
    sensitive_cells = sensitive_cells or []

    def add_issue(
        rule_id: str,
        severity: str,
        message: str,
        remediation: str,
        affected_items: list[Any],
        provenance: Any,
    ):
        issues.append({
            "rule_id": rule_id,
            "severity": severity,  # blocking | warning | info
            "message": message,
            "remediation": remediation,
            "affected_items": affected_items,
            "provenance": provenance,
            "resolved_status": "open",
        })

    # 1. Mapping chưa xác nhận
    if pending_mappings:
        add_issue(
            "HC-MAPPING-PENDING",
            "blocking",
            f"Còn {len(pending_mappings)} mục mapping/cảnh báo chưa được Admin xác nhận.",
            "Vào trang Mapping để xác nhận, chỉnh sửa hoặc từ chối từng mục trước khi công bố.",
            [m.get("source_column_or_cell") for m in pending_mappings[:10]],
            [{"source": m.get("source_column_or_cell")} for m in pending_mappings[:5]],
        )

    # 2. Kiểm tra từng buổi: trường bắt buộc, giảng viên, trạng thái phòng, tên nhân sự
    for idx, it in enumerate(items):
        label = f"{it.get('class_name')} {it.get('session_type')} {it.get('session_number')} ({it.get('date')})"
        item_ref = it.get("id") or label
        prov = it.get("provenance") or []

        st = _to_minutes(it.get("start_time", ""))
        en = _to_minutes(it.get("end_time", ""))
        missing_fields = [f for f in ("date", "class_name", "session_type", "topic") if not str(it.get(f) or "").strip()]
        if st < 0 or en < 0 or st >= en:
            missing_fields.append("start_time/end_time hợp lệ")
        if missing_fields:
            add_issue(
                "HC-REQ",
                "blocking",
                f"Buổi {label} thiếu hoặc sai định dạng trường bắt buộc: {', '.join(missing_fields)}.",
                "Bổ sung đầy đủ ngày, lớp, loại buổi, giờ bắt đầu < giờ kết thúc và chủ đề ở trang Lịch nháp.",
                [item_ref],
                prov,
            )

        instructors = _split_csv_list(it.get("instructor", ""))
        if not instructors:
            add_issue(
                "HC-09",
                "blocking",
                f"Buổi {label} chưa có giảng viên phụ trách.",
                "Kiểm tra lại file phân công giảng dạy hoặc gán giảng viên trực tiếp trên bản nháp.",
                [item_ref],
                prov,
            )
        elif canonical_staff:
            non_canon = [g for g in instructors if g not in canonical_staff]
            if non_canon:
                add_issue(
                    "SC-STAFF-ALIAS",
                    "warning",
                    f"Buổi {label} có tên giảng viên lệch danh mục chuẩn Nhan_su: {', '.join(non_canon)}.",
                    "Chuẩn hoá tên giảng viên theo cột 'Tên khớp chuẩn' của sheet Nhan_su.",
                    [item_ref],
                    prov,
                )

        room_status = (it.get("room_status") or "").lower()
        room_str = str(it.get("room") or "").strip()
        is_online = room_status == "online" or room_str.lower() == "online"
        if not is_online:
            if room_status in ("pending", "tentative") or not room_str:
                add_issue(
                    "HC-ROOM-STATUS",
                    "blocking",
                    f"Buổi {label} có trạng thái phòng '{room_status or 'trống'}' ({room_str or 'chưa có mã phòng'}) — chưa được xác nhận chính thức.",
                    "Liên hệ Ban đào tạo xác nhận mã phòng chính thức rồi cập nhật room_status thành 'confirmed' trên bản nháp.",
                    [item_ref],
                    prov,
                )

    # 3. Kiểm tra trùng theo cặp buổi chồng giờ (HC-01, HC-02, HC-03, HC-11)
    for i in range(len(items)):
        a = items[i]
        a_st, a_en = _to_minutes(a.get("start_time", "")), _to_minutes(a.get("end_time", ""))
        if a_st < 0 or a_en < 0:
            continue
        a_label = f"{a.get('class_name')} {a.get('session_type')} {a.get('session_number')}"
        a_ref = a.get("id") or f"{a_label} ({a.get('date')})"

        for j in range(i + 1, len(items)):
            b = items[j]
            if a.get("date") != b.get("date"):
                continue
            b_st, b_en = _to_minutes(b.get("start_time", "")), _to_minutes(b.get("end_time", ""))
            if not _intervals_overlap(a_st, a_en, b_st, b_en):
                continue

            b_label = f"{b.get('class_name')} {b.get('session_type')} {b.get('session_number')}"
            b_ref = b.get("id") or f"{b_label} ({b.get('date')})"
            both_prov = (a.get("provenance") or [])[:2] + (b.get("provenance") or [])[:2]

            # HC-01: Trùng giảng viên
            lec_a = set(_split_csv_list(a.get("instructor", "")))
            lec_b = set(_split_csv_list(b.get("instructor", "")))
            common_lec = sorted(lec_a & lec_b)
            if common_lec:
                add_issue(
                    "HC-01",
                    "blocking",
                    f"Trùng giảng viên ({', '.join(common_lec)}) ngày {a.get('date')}: {a_label} ({a.get('start_time')}-{a.get('end_time')}) và {b_label} ({b.get('start_time')}-{b.get('end_time')}).",
                    "Điều chỉnh giảng viên thay thế hoặc đổi khung giờ của một trong hai buổi.",
                    [a_ref, b_ref],
                    both_prov,
                )

            # HC-02: Trùng lớp / học viên
            cls_a = _expand_classes(a.get("class_name", ""))
            cls_b = _expand_classes(b.get("class_name", ""))
            common_cls = sorted(cls_a & cls_b)
            if common_cls:
                add_issue(
                    "HC-02",
                    "blocking",
                    f"Lớp {', '.join(common_cls)} có hai buổi chồng giờ ngày {a.get('date')}: {a_label} ({a.get('start_time')}-{a.get('end_time')}) và {b_label} ({b.get('start_time')}-{b.get('end_time')}).",
                    "Tách khung giờ học cho hai buổi bị chồng chéo.",
                    [a_ref, b_ref],
                    both_prov,
                )

            # HC-03: Trùng trợ giảng / coach
            asst_a = {re.sub(r"^Key:\s*", "", x).strip() for x in (a.get("assistants") or [])}
            asst_b = {re.sub(r"^Key:\s*", "", x).strip() for x in (b.get("assistants") or [])}
            common_asst = sorted(x for x in (asst_a & asst_b) if x)
            if common_asst:
                add_issue(
                    "HC-03",
                    "blocking",
                    f"Trùng coach/trợ giảng ({', '.join(common_asst)}) ngày {a.get('date')}: {a_label} và {b_label}.",
                    "Phân công coach thay thế ở một trong hai buổi.",
                    [a_ref, b_ref],
                    both_prov,
                )

            # HC-11: Trùng phòng vật lý giữa hai buổi offline độc lập
            a_onl = (a.get("room_status") or "").lower() == "online" or str(a.get("room") or "").lower() == "online"
            b_onl = (b.get("room_status") or "").lower() == "online" or str(b.get("room") or "").lower() == "online"
            if not a_onl and not b_onl:
                rooms_a = set(re.findall(r"\b[A-Z]\d{3}\b", str(a.get("room") or "").upper()))
                rooms_b = set(re.findall(r"\b[A-Z]\d{3}\b", str(b.get("room") or "").upper()))
                common_rooms = sorted(rooms_a & rooms_b)
                if common_rooms:
                    add_issue(
                        "HC-11",
                        "blocking",
                        f"Trùng phòng {', '.join(common_rooms)} ngày {a.get('date')}: {a_label} ({a.get('start_time')}-{a.get('end_time')}) và {b_label} ({b.get('start_time')}-{b.get('end_time')}).",
                        "Chuyển một buổi sang phòng trống khác hoặc sửa khung giờ tránh trùng.",
                        [a_ref, b_ref],
                        both_prov,
                    )

    # 4. Mâu thuẫn giữa các file/sheet nguồn (ví dụ bản xuất vs bản chép vs lịch lab dk:)
    for conf in source_conflicts:
        add_issue(
            "HC-SOURCE-CONFLICT",
            "blocking",
            (
                f"Mâu thuẫn nguồn tại {conf['session_key']}: nguồn chính ({conf['primary_ts'] or 'N/A'}) ghi "
                f"{', '.join(conf['primary_rooms']) or 'chưa có'} [{conf['primary_status']}], "
                f"trong khi bản đối chiếu ({conf['secondary_ts'] or 'N/A'}) ghi "
                f"{', '.join(conf['secondary_rooms']) or 'chưa có'} [{conf['secondary_status']}]."
            ),
            "Admin đối chiếu thời điểm cập nhật của hai bảng tính rồi xác nhận bản có hiệu lực.",
            [conf["session_key"]],
            [conf["primary_prov"], conf["secondary_prov"]],
        )

    # 5. Thiếu ánh xạ học viên-lớp-phòng để kiểm sức chứa HC-07
    if learners_count > 0 and not learners_has_class_mapping:
        add_issue(
            "HC-07-DATA",
            "warning",
            f"Đã nạp {learners_count} học viên nhưng thiếu bảng ánh xạ học viên–lớp–nhóm–phòng; chưa đủ dữ liệu kiểm chứng sức chứa từng phòng (không tự chia đều).",
            "Upload thêm bảng phân lớp/phân nhóm học viên nếu cần kiểm tra sức chứa chi tiết theo phòng.",
            [],
            [],
        )

    # 6. Ô chứa chuỗi nghi prompt injection
    inj_cells = [c for c in sensitive_cells if "prompt_injection" in str(c.get("sensitivity_flag") or "")]
    if inj_cells:
        add_issue(
            "HC-INJECTION-CELL",
            "warning",
            f"Phát hiện {len(inj_cells)} ô chứa chuỗi giống chỉ dẫn điều khiển hệ thống; hệ thống coi là dữ liệu thuần và bỏ qua chỉ dẫn.",
            "Admin kiểm tra lại nội dung ô nguồn để loại bỏ văn bản bất thường trước khi xuất thông báo.",
            [f"{c.get('workbook')} :: {c.get('sheet')} :: {c.get('cell_range')}" for c in inj_cells[:5]],
            [{"file": c.get("workbook"), "sheet": c.get("sheet"), "cell": c.get("cell_range")} for c in inj_cells[:5]],
        )

    # 7. Đơn đổi buổi chưa đồng bộ vào sheet
    unsynced_swaps = [
        sw for sw in swap_requests
        if "chưa cập nhật" in (sw.get("note") or "").lower() or not sw.get("processed")
    ]
    if unsynced_swaps:
        add_issue(
            "SC-SWAP-UNSYNCED",
            "warning",
            f"Có {len(unsynced_swaps)} yêu cầu trong 'Đổi buổi (form)' chưa xử lý hoặc ghi 'chưa cập nhật sheet'.",
            "Xác minh lại phân công thực tế của các coach liên quan trước khi duyệt công bố.",
            [f"{sw['coach']} ({sw['current_session']})" for sw in unsynced_swaps[:5]],
            [sw["provenance"] for sw in unsynced_swaps[:5]],
        )

    blocking_count = sum(1 for x in issues if x["severity"] == "blocking")
    warning_count = sum(1 for x in issues if x["severity"] == "warning")

    # Bảng tóm tắt trạng thái theo từng quy tắc cốt lõi
    rule_catalog = [
        ("HC-REQ", "Đủ trường bắt buộc & khung giờ hợp lệ"),
        ("HC-01", "Không trùng giờ giảng viên"),
        ("HC-02", "Không trùng giờ lớp / học viên"),
        ("HC-03", "Không trùng ca trợ giảng / coach"),
        ("HC-09", "Mọi buổi đều có giảng viên"),
        ("HC-11", "Không trùng phòng vật lý"),
        ("HC-ROOM-STATUS", "Phòng offline đã xác nhận (không còn pending/dk:)"),
        ("HC-SOURCE-CONFLICT", "Không có mâu thuẫn chưa phân xử giữa các file/sheet"),
        ("HC-MAPPING-PENDING", "Mọi mapping mơ hồ đã được Admin xác nhận"),
        ("HC-07-DATA", "Độ đủ dữ liệu kiểm chứng sức chứa (cảnh báo nếu thiếu)"),
        ("HC-INJECTION-CELL", "Bảo vệ chống chỉ dẫn nhúng trong ô Excel"),
        ("SC-SWAP-UNSYNCED", "Đồng bộ đơn đổi ca (Đổi buổi form)"),
    ]
    rule_status_rows = []
    for rid, title in rule_catalog:
        matched = [i for i in issues if i["rule_id"] == rid]
        if any(i["severity"] == "blocking" for i in matched):
            st_label = "blocking"
        elif matched:
            st_label = "warning"
        else:
            st_label = "pass"
        rule_status_rows.append({
            "rule_id": rid,
            "title": title,
            "status": st_label,
            "issue_count": len(matched),
        })

    return {
        "ruleset_version": RULESET_VERSION,
        "can_publish": blocking_count == 0 and len(items) > 0,
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "total_items": len(items),
        "rule_statuses": rule_status_rows,
        "issues": issues,
        "summary_json": json.dumps({
            "can_publish": blocking_count == 0 and len(items) > 0,
            "blocking_count": blocking_count,
            "warning_count": warning_count,
            "total_items": len(items),
        }, ensure_ascii=False),
    }
