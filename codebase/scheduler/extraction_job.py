"""Run one admin extraction at a time with a job-owned llama.cpp process."""
from io import BytesIO
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from urllib.error import URLError

from openpyxl import load_workbook

from ..ai import llama_server
from .extract_schedule import COACH_SHEETS, TEACHING_SHEET, run_extraction
from .security import scan_payload

class ExtractionJob:
    def __init__(self, root, logger):
        self.root = root.resolve()
        self.logger = logger
        self.lock = Lock()
        self.state = None

    def snapshot(self):
        with self.lock:
            return dict(self.state) if self.state else None

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def update_tokens(self, prompt, generated, rate, finished):
        with self.lock:
            state = self.state
            if finished:
                state["completed_prompt"] += prompt
                state["completed_generated"] += generated
                prompt = generated = 0
            state.update(
                prompt_tokens=state["completed_prompt"] + prompt,
                generated_tokens=state["completed_generated"] + generated,
                tokens_per_second=rate,
            )

    def start_sheet(self, sheet):
        with self.lock:
            self.state.update(
                message="Đang đọc sheet " + sheet, sheet=sheet,
                sheet_start_tokens=self.state["completed_prompt"] + self.state["completed_generated"],
            )

    def start(self, owner, files, executable, model):
        with self.lock:
            if self.state and self.state["status"] == "running":
                raise ValueError("Đang có một lượt trích xuất AI.")
            ident = secrets.token_hex(12)
            self.state = dict(
                id=ident, owner=owner, status="running", message="Đang quét hai workbook.",
                completed_prompt=0, completed_generated=0, prompt_tokens=0,
                generated_tokens=0, tokens_per_second=None,
            )
            worker = Thread(target=self.run, args=(ident, files, executable, model), daemon=True)
            try:
                worker.start()
            except RuntimeError:
                self.state = None
                raise
        return ident

    def report_path(self, ident):
        return self.root / "extractions" / (ident + ".json")

    def run(self, ident, files, executable, model):
        try:
            with TemporaryDirectory(prefix="a5-model-") as temp:
                sources = {}
                for name, payload in files:
                    scan_payload(payload)
                    with BytesIO(payload) as workbook:
                        book = load_workbook(workbook, read_only=True, keep_links=False)
                        try:
                            sheets = set(book.sheetnames)
                        finally:
                            book.close()
                    kind = "teaching" if TEACHING_SHEET in sheets else "coaches" if set(COACH_SHEETS) <= sheets else ""
                    if not kind or kind in sources:
                        raise ValueError("Chọn một workbook lịch giảng dạy K9 và một workbook lịch Lab Coach K9.")
                    folder = Path(temp) / kind
                    folder.mkdir()
                    path = folder / name
                    path.write_bytes(payload)
                    sources[kind] = path

                self.update(message="Đang khởi động llama-server và nạp GGUF.")
                with llama_server(executable, model) as port:
                    report = run_extraction(
                        sources["teaching"], sources["coaches"], self.report_path(ident), port=port,
                        progress=self.start_sheet,
                        stats=self.update_tokens,
                    )
            issue_count = len(report["model_extraction_issues"])
            message = (
                "Đã lưu báo cáo một phần và dừng llama-server."
                if issue_count else "Đã trích xuất xong và dừng llama-server."
            )
            self.update(status="done", message=message, issue_count=issue_count,
                        fact_count=len(report["model_facts_for_review"]))
        except URLError:
            self.logger.exception("Lost connection to llama-server during extraction")
            self.update(status="error", message="Mất kết nối với llama-server trong khi trích xuất.")
        except ValueError as exc:
            self.update(status="error", message=str(exc))
        except Exception:
            self.logger.exception("Schedule extraction failed")
            self.update(status="error", message="Không hoàn tất trích xuất AI. Kiểm tra nhật ký ứng dụng.")

