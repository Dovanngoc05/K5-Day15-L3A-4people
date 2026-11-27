"""Cấu hình ứng dụng đọc từ biến môi trường / `.env`, tuyệt đối không hard-code bí mật."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from codebase.ai_service import load_local_env
from codebase.file_safety import UploadLimits

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    frontend_origins: tuple[str, ...]
    cookie_secure: bool
    session_ttl_hours: int
    upload_limits: UploadLimits
    ai_budget_usd_per_project: float

    @classmethod
    def from_env(cls) -> "Settings":
        load_local_env(ROOT_DIR / ".env")
        db_url = os.environ.get("DATABASE_URL") or "sqlite:///./.local_data/app.db"
        up_dir = Path(os.environ.get("UPLOAD_STORAGE_DIR") or str(ROOT_DIR / ".local_data" / "uploads"))
        if not up_dir.is_absolute():
            up_dir = (ROOT_DIR / up_dir).resolve()
        origin_raw = os.environ.get("FRONTEND_ORIGIN") or "http://localhost:5173,http://127.0.0.1:5173"
        origins = tuple(o.strip().rstrip("/") for o in origin_raw.split(",") if o.strip())
        cookie_secure = (os.environ.get("SESSION_COOKIE_SECURE") or "false").strip().lower() == "true"
        max_mb = int(os.environ.get("MAX_UPLOAD_MB") or 10)
        limits = UploadLimits(
            max_upload_bytes=max_mb * 1024 * 1024,
            max_files_per_batch=int(os.environ.get("MAX_FILES_PER_BATCH") or 10),
            max_sheets=int(os.environ.get("MAX_SHEETS") or 30),
            max_rows=int(os.environ.get("MAX_ROWS") or 10_000),
            max_cols=int(os.environ.get("MAX_COLS") or 200),
            allow_xlsm=(os.environ.get("ALLOW_XLSM") or "false").strip().lower() == "true",
        )
        return cls(
            database_url=db_url,
            upload_dir=up_dir,
            frontend_origins=origins,
            cookie_secure=cookie_secure,
            session_ttl_hours=int(os.environ.get("SESSION_TTL_HOURS") or 12),
            upload_limits=limits,
            ai_budget_usd_per_project=float(os.environ.get("AI_BUDGET_USD_PER_PROJECT") or 1.0),
        )
