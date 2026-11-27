"""Mô hình dữ liệu SQLAlchemy 2 cho toàn bộ 12 bảng nghiệp vụ và xác thực."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")  # admin | viewer
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    course_code: Mapped[str] = mapped_column(String(60), nullable=False, default="AI20K-K9")
    classes_scope: Mapped[str] = mapped_column(String(160), nullable=False, default="L3A,L3B,L2A,L2B")
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    active_published_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    file_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pii_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="parsed")  # parsed | deleted | error
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceCell(Base):
    __tablename__ = "source_cells"
    __table_args__ = (
        Index("ix_source_cells_upload_sheet", "upload_id", "sheet"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True, nullable=False)
    workbook: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet: Mapped[str] = mapped_column(String(160), nullable=False)
    cell_range: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sensitivity_flag: Mapped[str] = mapped_column(String(60), nullable=False, default="normal")


class ScheduleVersion(Base):
    __tablename__ = "schedule_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_project_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="draft")  # draft | published | superseded
    base_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_upload_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    publish_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    __table_args__ = (
        Index("ix_schedule_items_ver_date_cls", "version_id", "date", "class_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    class_name: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)
    session_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_time: Mapped[str] = mapped_column(String(10), nullable=False)
    end_time: Mapped[str] = mapped_column(String(10), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    room: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    instructor: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    assistants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    room_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")  # confirmed | tentative | pending | online
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # passed | blocked
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    validation_run_id: Mapped[int] = mapped_column(ForeignKey("validation_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)  # blocking | warning | info
    message: Mapped[str] = mapped_column(Text, nullable=False)
    remediation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    affected_items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    resolved_status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class MappingDecision(Base):
    __tablename__ = "mapping_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True, nullable=False)
    source_column_or_cell: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_sample: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_field: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ai_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ai_rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_decision: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="needs_confirmation")
    final_value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    token_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # ok | cached | provider_error | budget_exceeded | disabled
    cached_response_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    actor_username: Mapped[str] = mapped_column(String(80), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False, default=utc_now)
    safe_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
