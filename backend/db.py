"""Kết nối SQLAlchemy 2 cho SQLite local, hỗ trợ thời gian UTC và múi giờ Asia/Ho_Chi_Minh."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import ROOT_DIR, Settings

HCM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_hcm_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(HCM_TZ).strftime("%Y-%m-%d %H:%M:%S (UTC+7)")


def make_engine(database_url: str | None = None):
    url = database_url or Settings.from_env().database_url
    if url.startswith("sqlite:///"):
        raw_path = url.replace("sqlite:///", "", 1)
        if raw_path != ":memory:":
            p = Path(raw_path)
            if not p.is_absolute():
                p = (ROOT_DIR / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{p.as_posix()}"

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_DEFAULT_ENGINE = None
_DEFAULT_SESSION_FACTORY = None


def init_session_factory(database_url: str | None = None):
    global _DEFAULT_ENGINE, _DEFAULT_SESSION_FACTORY
    _DEFAULT_ENGINE = make_engine(database_url)
    _DEFAULT_SESSION_FACTORY = sessionmaker(bind=_DEFAULT_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False)
    return _DEFAULT_ENGINE, _DEFAULT_SESSION_FACTORY


def get_session_factory():
    global _DEFAULT_SESSION_FACTORY
    if _DEFAULT_SESSION_FACTORY is None:
        init_session_factory()
    return _DEFAULT_SESSION_FACTORY


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
