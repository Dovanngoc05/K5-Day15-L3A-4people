"""Pydantic schemas cho REST API (request/response validation)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    course_code: str = Field(default="AI20K-K9", min_length=2, max_length=60)
    classes_scope: str = Field(default="L3A,L3B,L2A,L2B", max_length=160)
    ai_enabled: bool = True
    ai_budget_usd: float = Field(default=1.0, ge=0.0, le=1000.0)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    classes_scope: str | None = Field(default=None, max_length=160)
    ai_enabled: bool | None = None
    ai_budget_usd: float | None = Field(default=None, ge=0.0, le=1000.0)


class AnalyzeUploadRequest(BaseModel):
    redact_pii: bool = True


class MappingConfirmRequest(BaseModel):
    decision: str = Field(pattern="^(accepted|edited|rejected)$")
    final_field: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=300)


class VersionCreateRequest(BaseModel):
    upload_ids: list[int] | None = None
    from_version_id: int | None = None
    change_summary: str = Field(default="", max_length=300)


class ScheduleItemPatchRequest(BaseModel):
    date: str | None = Field(default=None, max_length=20)
    class_name: str | None = Field(default=None, max_length=40)
    start_time: str | None = Field(default=None, max_length=10)
    end_time: str | None = Field(default=None, max_length=10)
    topic: str | None = Field(default=None, max_length=255)
    room: str | None = Field(default=None, max_length=160)
    instructor: str | None = Field(default=None, max_length=160)
    room_status: str | None = Field(default=None, pattern="^(confirmed|tentative|pending|online)$")
    reason: str = Field(default="Admin chỉnh sửa thủ công", max_length=240)


class PublishVersionRequest(BaseModel):
    confirm: bool
    publish_key: str | None = Field(default=None, max_length=80)
    change_summary: str | None = Field(default=None, max_length=300)


class GenericMessage(BaseModel):
    ok: bool = True
    message: str


class BatchMappingItemRequest(BaseModel):
    id: int
    decision: str = Field(pattern="^(accepted|edited|rejected)$")
    final_field: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=300)


class BatchMappingConfirmRequest(BaseModel):
    items: list[BatchMappingItemRequest] = Field(min_length=1, max_length=200)
    data: Any = None
