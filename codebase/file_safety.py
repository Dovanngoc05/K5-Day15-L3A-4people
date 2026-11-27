"""Kiểm tra an toàn file Excel upload, chống lỗ hổng OOXML và phát hiện/ẩn danh PII.

Tầng bảo vệ trước khi đưa workbook vào `codebase/excel_reader.py`:
  - Kiểm tra phần mở rộng (.xlsx; .xlsm chỉ cho phép khi cấu hình, vẫn chặn macro).
  - Kiểm tra giới hạn dung lượng, magic header ZIP (PK\\x03\\x04), chống ZIP bomb, chống path traversal.
  - Chặn VBA macro (vbaProject.bin, vbaData.xml), ActiveX/OLE nhúng, tệp thực thi, XXE (<!DOCTYPE/<!ENTITY),
    công thức thực thi lệnh (=CMD|, =WEBSERVICE(, javascript:).
  - Phát hiện chuỗi nghi prompt injection và phân loại độ nhạy PII (email, SĐT, mã học viên, họ tên).
  - Lưu file bằng UUID4 ngoài thư mục public, không dùng tên file người dùng làm đường dẫn trên đĩa.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ALLOWED_EXTENSIONS = {".xlsx"}

DANGEROUS_FORMULA_PATTERNS = [
    re.compile(r"=\s*(cmd|powershell|wscript|cscript|mshta)\s*\|", re.IGNORECASE),
    re.compile(r"=\s*webservice\s*\(", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"<\s*script\b", re.IGNORECASE),
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"system\s+override", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"bỏ\s+qua\s+(mọi|tất\s+cả)\s+(quy\s+tắc|hướng\s+dẫn|cảnh\s+báo)", re.IGNORECASE),
    re.compile(r"tự\s+động\s+(công\s+bố|publish|gửi)", re.IGNORECASE),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?84|0)(?:[\s.\-]?\d){8,10}\b")
STUDENT_ID_RE = re.compile(r"\b2A20\d{5,}\b|\bL\d{4,5}\b")


@dataclass(frozen=True)
class UploadLimits:
    max_upload_bytes: int = 10 * 1024 * 1024
    max_files_per_batch: int = 10
    max_sheets: int = 30
    max_rows: int = 10_000
    max_cols: int = 200
    max_uncompressed_bytes: int = 50 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_zip_entries: int = 500
    allow_xlsm: bool = False


def sanitize_user_text(value: object, max_len: int = 300) -> str:
    """Làm sạch text người dùng nhập vào form/API, loại bỏ ký tự điều khiển và thẻ HTML."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())[:max_len]


def sanitize_filename(filename: str | None) -> str:
    """Chuẩn hoá tên hiển thị (không bao giờ dùng làm path lưu đĩa)."""
    raw = str(filename or "")
    # Tách theo cả / và \ để loại bỏ đường dẫn thư mục
    leaf = raw.replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u00C0-\u024F\u1E00-\u1EFF ]+", "_", leaf).strip(" .")
    if not cleaned:
        return "workbook.xlsx"
    return cleaned[:120]


def has_abnormal_filename(filename: str | None) -> bool:
    """Phát hiện tên file có dấu hiệu path traversal hoặc ký tự null."""
    raw = str(filename or "")
    if not raw.strip() or "\x00" in raw:
        return True
    if ".." in raw or "/" in raw or "\\" in raw:
        return True
    return False


def validate_excel_bytes(
    filename: str | None,
    payload: bytes,
    limits: UploadLimits | None = None,
) -> dict:
    """Kiểm tra an toàn file Excel trước khi lưu và đọc."""
    limits = limits or UploadLimits()
    raw_name = str(filename or "")
    safe_display_name = sanitize_filename(raw_name)
    ext = Path(safe_display_name).suffix.lower()
    allowed = {".xlsx", ".xlsm"} if limits.allow_xlsm else DEFAULT_ALLOWED_EXTENSIONS
    sha256 = hashlib.sha256(payload or b"").hexdigest()

    errors: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    if has_abnormal_filename(raw_name):
        errors.append("Tên file chứa ký tự hoặc đường dẫn bất thường (path traversal).")

    if ext not in allowed:
        allowed_txt = ", ".join(sorted(allowed))
        errors.append(f"Định dạng '{ext or '(không có)'}' không được phép. Chỉ chấp nhận: {allowed_txt}.")
    else:
        checks.append(f"Phần mở rộng hợp lệ ({ext})")

    size = len(payload or b"")
    if size == 0:
        errors.append("File rỗng (0 byte).")
    elif size > limits.max_upload_bytes:
        errors.append(f"Kích thước file ({size:,} bytes) vượt giới hạn {limits.max_upload_bytes:,} bytes.")
    else:
        checks.append(f"Kích thước hợp lệ ({size:,} bytes)")

    if not errors:
        if not payload.startswith(b"PK\x03\x04"):
            errors.append("File không đúng chữ ký định dạng OOXML/ZIP hợp lệ.")
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                    infos = zf.infolist()
                    if len(infos) > limits.max_zip_entries:
                        errors.append(f"Số phần tử nén trong file quá lớn ({len(infos)} > {limits.max_zip_entries}).")

                    total_uncompressed = 0
                    has_workbook_xml = False
                    for info in infos:
                        member = info.filename.replace("\\", "/")
                        if member.startswith("/") or ".." in member.split("/"):
                            errors.append(f"Phát hiện đường dẫn nguy hiểm trong gói ZIP: {member}")
                            continue
                        total_uncompressed += info.file_size
                        if info.compress_size > 0 and (info.file_size / info.compress_size) > limits.max_compression_ratio:
                            errors.append(f"Nghi ngờ ZIP bomb tại '{member}' (tỷ lệ nén vượt {limits.max_compression_ratio}x).")

                        low = member.lower()
                        if low == "xl/workbook.xml":
                            has_workbook_xml = True

                        if "vbaproject.bin" in low or "vbadata.xml" in low:
                            errors.append(f"Từ chối workbook chứa VBA macro ({member}).")
                        if low.startswith("xl/activex/") or low.startswith("xl/embeddings/"):
                            errors.append(f"Từ chối workbook chứa đối tượng nhúng ActiveX/OLE ({member}).")
                        if low.endswith((".exe", ".dll", ".bat", ".ps1", ".vbs", ".js", ".scr", ".msi")):
                            errors.append(f"Từ chối tệp thực thi nhúng trong workbook ({member}).")

                        if low.endswith(".xml") and info.file_size <= 5 * 1024 * 1024:
                            raw_xml = zf.read(info).decode("utf-8", errors="ignore")
                            low_xml = raw_xml.lower()
                            if "<!doctype" in low_xml or "<!entity" in low_xml:
                                errors.append(f"Từ chối XML chứa DOCTYPE/ENTITY (nguy cơ XXE) tại {member}.")
                            for pat in DANGEROUS_FORMULA_PATTERNS:
                                if pat.search(raw_xml):
                                    errors.append(f"Từ chối nội dung công thức/script nguy hiểm tại {member}.")
                                    break
                            for pat in PROMPT_INJECTION_PATTERNS:
                                if pat.search(raw_xml):
                                    warnings.append(
                                        f"Phát hiện nội dung giống chỉ dẫn điều khiển AI tại {member} — hệ thống coi là dữ liệu không đáng tin cậy."
                                    )
                                    break

                    if total_uncompressed > limits.max_uncompressed_bytes:
                        errors.append(
                            f"Dung lượng giải nén ({total_uncompressed:,} bytes) vượt ngưỡng {limits.max_uncompressed_bytes:,} bytes."
                        )
                    if not has_workbook_xml:
                        errors.append("Gói ZIP thiếu xl/workbook.xml (không phải workbook Excel hợp lệ).")
                    if not errors:
                        checks.append(f"OOXML an toàn ({len(infos)} phần tử, không macro/ActiveX/XXE)")
            except zipfile.BadZipFile:
                errors.append("File Excel bị hỏng hoặc không phải định dạng ZIP OOXML.")

    return {
        "safe": not errors,
        "safe_display_name": safe_display_name,
        "ext": ext,
        "size_bytes": size,
        "sha256": sha256,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }


def save_safe_upload(storage_dir: Path, payload: bytes, ext: str = ".xlsx") -> tuple[str, Path]:
    """Lưu file Excel vào thư mục local bằng tên UUID4 (không bao giờ dùng tên gốc của người dùng)."""
    safe_ext = ext if ext in (".xlsx", ".xlsm") else ".xlsx"
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex
    target = (storage_dir / f"{file_id}{safe_ext}").resolve()
    if target.parent != storage_dir.resolve():
        raise ValueError("Đường dẫn lưu trữ không hợp lệ.")
    target.write_bytes(payload)
    return file_id, target


def classify_cell_sensitivity(sheet_name: str, header_hint: str, value: object) -> str:
    """Phân loại độ nhạy dữ liệu của một ô Excel."""
    if value is None:
        return "normal"
    text = str(value).strip()
    if not text:
        return "normal"

    flags: list[str] = []
    for pat in PROMPT_INJECTION_PATTERNS:
        if pat.search(text):
            flags.append("prompt_injection_suspect")
            break
    if EMAIL_RE.search(text):
        flags.append("pii_email")
    if PHONE_RE.search(text) and not re.match(r"^\d{4}-\d{2}-\d{2}", text):
        flags.append("pii_phone")
    if STUDENT_ID_RE.search(text):
        flags.append("pii_student_id")

    low_sheet = (sheet_name or "").lower()
    low_header = (header_hint or "").lower()
    if (
        ("learner" in low_sheet or any(k in low_header for k in ("full_name", "họ tên", "ho ten", "họ và tên")))
        and len(text.split()) >= 2
        and not re.match(r"^(lecturer|lab\s*coach|support)\b", text, re.IGNORECASE)
        and "pii_student_id" not in flags
        and "pii_email" not in flags
    ):
        flags.append("pii_name")

    return ",".join(flags) if flags else "normal"


def redact_pii_text(text: str, sensitivity_flag: str = "") -> str:
    """Ẩn danh email, SĐT, mã học viên và tên cá nhân trước khi gửi ngữ cảnh sang AI."""
    if not text:
        return ""
    if "pii_name" in (sensitivity_flag or ""):
        return "[TEN_AN_DANH]"
    out = EMAIL_RE.sub("[EMAIL_AN_DANH]", text)
    out = STUDENT_ID_RE.sub("[MA_HV_AN_DANH]", out)
    out = PHONE_RE.sub("[SDT_AN_DANH]", out)
    return out


def sanitize_formula_export(value: object) -> object:
    """Ngăn formula injection khi xuất/hiển thị giá trị chuỗi."""
    if not isinstance(value, str):
        return value
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    if cleaned and cleaned[0] in ("=", "+", "-", "@"):
        return "'" + cleaned
    return cleaned
