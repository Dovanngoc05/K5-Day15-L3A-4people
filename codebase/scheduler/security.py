"""Bounded XLSX parsing and real antivirus integration, failing closed."""
from io import BytesIO
from pathlib import Path, PurePosixPath
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from defusedxml import ElementTree
from werkzeug.utils import secure_filename


def scanner_command():
    configured = os.environ.get("CLAMSCAN_PATH")
    clam = configured or shutil.which("clamscan")
    if clam and Path(clam).is_file():
        return "ClamAV", [str(clam), "--no-summary", "--infected"]
    if os.name == "nt":
        root = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft/Windows Defender/Platform"
        candidates = sorted(root.glob("*/MpCmdRun.exe"), reverse=True)
        fallback = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Windows Defender/MpCmdRun.exe"
        if fallback.is_file():
            candidates.append(fallback)
        if candidates:
            return "Microsoft Defender", [str(candidates[0]), "-Scan", "-ScanType", "3", "-DisableRemediation", "-File"]
    return None, None


def scan_payload(payload):
    engine, command = scanner_command()
    if not command:
        raise ValueError("Chưa có trình quét virus. Cài ClamAV, cập nhật freshclam và đặt CLAMSCAN_PATH, hoặc bật Microsoft Defender. File chưa được nhập.")
    with tempfile.TemporaryDirectory(prefix="a5-scan-") as folder:
        target = Path(folder) / "upload.xlsx"
        target.write_bytes(payload)
        try:
            result = subprocess.run(command + [str(target)], capture_output=True, timeout=90, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Không hoàn tất quét virus; file bị chặn.") from exc
        if result.returncode != 0:
            if engine == "Microsoft Defender":
                error_code = re.search(rb"\bhr\s*=\s*(0x[0-9a-f]{8})\b", result.stdout + b"\n" + result.stderr, re.I)
                if error_code:
                    code = error_code.group(1).decode("ascii")
                    raise ValueError(
                        f"Microsoft Defender không quét được file (mã {code}). "
                        "Kiểm tra Microsoft Defender Antivirus trong Windows Security "
                        "hoặc cấu hình ClamAV bằng CLAMSCAN_PATH. File chưa được nhập."
                    )
            elif result.returncode == 1:
                raise ValueError("ClamAV phát hiện nguy cơ. File chưa được nhập.")
            else:
                raise ValueError(
                    f"ClamAV không quét được file (mã thoát {result.returncode}). "
                    "Kiểm tra cài đặt và cập nhật cơ sở dữ liệu virus. File chưa được nhập."
                )
            raise ValueError(
                f"Microsoft Defender báo phát hiện nguy cơ hoặc lỗi quét (mã thoát {result.returncode}). "
                "Kiểm tra Windows Security. File chưa được nhập."
            )
    return engine


def inspect_xlsx(filename, payload):
    name = secure_filename(filename or "")
    if not name or Path(name).suffix.lower() != ".xlsx":
        raise ValueError("Chỉ nhận .xlsx không macro. Chuyển .xls/.xlsm sang .xlsx trước khi nhập.")
    if not payload or len(payload) > 10 * 1024 * 1024:
        raise ValueError("Mỗi file tối đa 10 MB và không được rỗng.")
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 3000 or len(names) != len(set(names)) or sum(i.file_size for i in infos) > 40*1024*1024:
                raise ValueError("Workbook vượt giới hạn giải nén hoặc chứa entry trùng.")
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError("File không phải workbook Excel hợp lệ.")
            cell_count = 0
            merge_cells = 0
            def check_reference(reference):
                match=re.fullmatch(r"([A-Z]{1,3})(\d{1,7})",reference)
                if not match:
                    raise ValueError("Toạ độ ô không hợp lệ.")
                col=0
                for char in match[1]:
                    col=col*26+ord(char)-64
                row=int(match[2])
                if row<1 or col*row>500_000:
                    raise ValueError("Kích thước sheet hoặc vùng gộp quá lớn.")
                return col,row
            for info in infos:
                lower = info.filename.lower()
                if info.flag_bits & 1 or ".." in PurePosixPath(lower).parts or lower.startswith("/") or "\\" in lower:
                    raise ValueError("ZIP có cấu trúc không hợp lệ hoặc mã hoá.")
                if any(part in lower for part in ["vbaproject", "embeddings/", "externallinks/", "activex/", "customui/"]):
                    raise ValueError("Workbook chứa macro, đối tượng nhúng hoặc liên kết dữ liệu ngoài.")
                if lower.endswith((".xml", ".rels")):
                    root = ElementTree.fromstring(archive.read(info))
                    if lower.startswith("xl/worksheets/") and lower.endswith(".xml"):
                        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                        cell_count += len(root.findall(".//m:c", ns))
                        dimension = root.find("m:dimension", ns)
                        if dimension is not None:
                            end = dimension.get("ref", "A1").split(":")[-1]
                            check_reference(end)
                        for cell in root.findall(".//m:c",ns):
                            check_reference(cell.get("r","A1"))
                        for merged in root.findall("m:mergeCells/m:mergeCell",ns):
                            parts=merged.get("ref","").split(":")
                            left=check_reference(parts[0])
                            right=check_reference(parts[-1])
                            merge_cells+=(right[0]-left[0]+1)*(right[1]-left[1]+1)
                            if merge_cells>500_000:
                                raise ValueError("Có quá nhiều ô gộp.")
                    if lower.endswith(".rels"):
                        for relationship in root:
                            if relationship.get("TargetMode") == "External":
                                target = relationship.get("Target", "")
                                if not relationship.get("Type", "").endswith("/hyperlink") or not target.startswith("https://"):
                                    raise ValueError("Liên kết ngoài không được phép.")
            if cell_count > 500_000:
                raise ValueError("Workbook có quá nhiều ô.")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("Excel bị hỏng hoặc không đúng định dạng.") from exc
    return name
