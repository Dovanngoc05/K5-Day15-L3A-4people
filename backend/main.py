"""FastAPI Backend cho Trợ lý tổng hợp và kiểm tra lịch đào tạo AI20K từ nhiều file Excel."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from codebase.ai_service import get_ai_config, propose_mappings
from codebase.domain_extractor import extract_workbook_bundle
from codebase.excel_reader import read_excel_files
from codebase.file_safety import sanitize_user_text, save_safe_upload, validate_excel_bytes
from codebase.validator import run_deterministic_validation

from .auth import (
    SESSION_COOKIE_NAME,
    check_rate_limit,
    clear_login_failures,
    create_user_session,
    dummy_verify,
    record_login_failure,
    require_admin,
    require_authenticated,
    verify_password,
)
from .config import Settings
from .db import get_db, init_session_factory, to_hcm_iso, utc_now
from .models import (
    AiRun,
    AuditLog,
    MappingDecision,
    Project,
    ScheduleItem,
    ScheduleVersion,
    SourceCell,
    Upload,
    User,
    UserSession,
    ValidationIssue,
    ValidationRun,
)
from .schemas import (
    AnalyzeUploadRequest,
    BatchMappingConfirmRequest,
    LoginRequest,
    MappingConfirmRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    PublishVersionRequest,
    ScheduleItemPatchRequest,
    VersionCreateRequest,
)


def _log_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else "anonymous",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        timestamp=utc_now(),
        safe_metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    ))


def _project_cfg(proj: Project) -> dict[str, Any]:
    try:
        return json.loads(proj.config_json or "{}")
    except Exception:
        return {}


def _serialize_item(it: ScheduleItem) -> dict[str, Any]:
    try:
        assistants = json.loads(it.assistants_json or "[]")
    except Exception:
        assistants = []
    try:
        provenance = json.loads(it.provenance_json or "[]")
    except Exception:
        provenance = []
    return {
        "id": it.id,
        "version_id": it.version_id,
        "date": it.date,
        "class_name": it.class_name,
        "session_type": it.session_type,
        "session_number": it.session_number,
        "start_time": it.start_time,
        "end_time": it.end_time,
        "topic": it.topic,
        "room": it.room,
        "instructor": it.instructor,
        "assistants": assistants,
        "room_status": it.room_status,
        "provenance": provenance,
    }


def _run_and_persist_validation(db: Session, ver: ScheduleVersion) -> ValidationRun:
    """Chạy kiểm tra xác định bằng code thuần trên toàn bộ ScheduleItem hiện tại của phiên bản."""
    db_items = db.execute(
        select(ScheduleItem).where(ScheduleItem.version_id == ver.id).order_by(ScheduleItem.date, ScheduleItem.start_time)
    ).scalars().all()
    items_payload = [_serialize_item(x) for x in db_items]

    try:
        upload_ids = [int(x) for x in json.loads(ver.source_upload_ids_json or "[]")]
    except Exception:
        upload_ids = []

    pending_maps: list[dict[str, Any]] = []
    source_conflicts: list[dict[str, Any]] = []
    swap_requests: list[dict[str, Any]] = []
    canonical_staff: set[str] = set()
    learners_count = 0
    learners_has_class = False
    sensitive_cells: list[dict[str, Any]] = []

    if upload_ids:
        maps = db.execute(
            select(MappingDecision).where(
                MappingDecision.upload_id.in_(upload_ids),
                MappingDecision.admin_decision == "needs_confirmation",
            )
        ).scalars().all()
        pending_maps = [{"id": m.id, "source_column_or_cell": m.source_column_or_cell} for m in maps]

        ups = db.execute(
            select(Upload).where(Upload.id.in_(upload_ids), Upload.status == "parsed")
        ).scalars().all()
        upload_recs = [
            {
                "upload_id": u.id,
                "original_name": u.original_name,
                "stored_path": u.stored_path,
                "uploaded_at": u.uploaded_at.isoformat(),
            }
            for u in ups
            if Path(u.stored_path).exists()
        ]
        if upload_recs:
            bundle = extract_workbook_bundle(upload_recs)
            canonical_staff = bundle["canonical_staff"]
            swap_requests = bundle["swap_requests"]
            learners_count = bundle["learners_count"]
            learners_has_class = bundle["learners_has_class_mapping"]

            # Lọc bỏ các conflict cho buổi mà Admin đã chỉnh sửa thủ công (`manual_override` trong provenance)
            overridden_keys = set()
            for it in items_payload:
                if any(isinstance(p, dict) and p.get("manual_override") for p in it["provenance"]):
                    overridden_keys.add(f"{it['class_name']} {it['session_type']} {it['session_number']} ({it['date']})")
            source_conflicts = [c for c in bundle["source_conflicts"] if c["session_key"] not in overridden_keys]

        sc_rows = db.execute(
            select(SourceCell).where(SourceCell.upload_id.in_(upload_ids), SourceCell.sensitivity_flag != "normal")
        ).scalars().all()
        sensitive_cells = [
            {"workbook": c.workbook, "sheet": c.sheet, "cell_range": c.cell_range, "sensitivity_flag": c.sensitivity_flag}
            for c in sc_rows
        ]

    started = utc_now()
    val_res = run_deterministic_validation(
        items_payload,
        pending_mappings=pending_maps,
        source_conflicts=source_conflicts,
        swap_requests=swap_requests,
        canonical_staff=canonical_staff,
        learners_count=learners_count,
        learners_has_class_mapping=learners_has_class,
        sensitive_cells=sensitive_cells,
    )
    finished = utc_now()

    summary_payload = {
        "can_publish": val_res["can_publish"],
        "blocking_count": val_res["blocking_count"],
        "warning_count": val_res["warning_count"],
        "total_items": val_res["total_items"],
        "rule_statuses": val_res["rule_statuses"],
    }
    vrun = ValidationRun(
        version_id=ver.id,
        ruleset_version=val_res["ruleset_version"],
        status="passed" if val_res["can_publish"] else "blocked",
        started_at=started,
        finished_at=finished,
        summary_json=json.dumps(summary_payload, ensure_ascii=False),
    )
    db.add(vrun)
    db.flush()

    for iss in val_res["issues"]:
        db.add(ValidationIssue(
            validation_run_id=vrun.id,
            rule_id=iss["rule_id"],
            severity=iss["severity"],
            message=iss["message"],
            remediation=iss["remediation"],
            affected_items_json=json.dumps(iss["affected_items"], ensure_ascii=False),
            provenance_json=json.dumps(iss["provenance"], ensure_ascii=False),
            resolved_status="open",
        ))
    db.flush()
    return vrun


def _latest_validation_payload(db: Session, version_id: int) -> dict[str, Any] | None:
    vrun = db.execute(
        select(ValidationRun).where(ValidationRun.version_id == version_id).order_by(desc(ValidationRun.id))
    ).scalars().first()
    if not vrun:
        return None
    issues = db.execute(
        select(ValidationIssue).where(ValidationIssue.validation_run_id == vrun.id).order_by(ValidationIssue.id)
    ).scalars().all()
    try:
        summary = json.loads(vrun.summary_json or "{}")
    except Exception:
        summary = {}
    return {
        "id": vrun.id,
        "version_id": vrun.version_id,
        "ruleset_version": vrun.ruleset_version,
        "status": vrun.status,
        "finished_at": to_hcm_iso(vrun.finished_at),
        "summary": summary,
        "issues": [
            {
                "id": iss.id,
                "rule_id": iss.rule_id,
                "severity": iss.severity,
                "message": iss.message,
                "remediation": iss.remediation,
                "affected_items": json.loads(iss.affected_items_json or "[]"),
                "provenance": json.loads(iss.provenance_json or "[]"),
                "resolved_status": iss.resolved_status,
            }
            for iss in issues
        ],
    }


def _revalidate_latest_draft_for_project(db: Session, project_id: int) -> dict[str, Any] | None:
    draft_ver = db.execute(
        select(ScheduleVersion)
        .where(ScheduleVersion.project_id == project_id, ScheduleVersion.status == "draft")
        .order_by(desc(ScheduleVersion.version_number))
    ).scalars().first()
    if not draft_ver:
        return None
    _run_and_persist_validation(db, draft_ver)
    return _latest_validation_payload(db, draft_ver.id)


def _create_draft_from_uploads_internal(
    db: Session,
    settings: Settings,
    admin: User,
    project_id: int,
    upload_ids: list[int] | None,
    change_summary: str,
) -> tuple[ScheduleVersion, ValidationRun]:
    existing = db.execute(select(ScheduleVersion).where(ScheduleVersion.project_id == project_id)).scalars().all()
    next_num = (max(v.version_number for v in existing) + 1) if existing else 1

    ups_q = select(Upload).where(Upload.project_id == project_id, Upload.status == "parsed")
    if upload_ids:
        ups_q = ups_q.where(Upload.id.in_(upload_ids))
    ups = db.execute(ups_q.order_by(Upload.id)).scalars().all()
    if not ups:
        raise HTTPException(status_code=400, detail="Chưa có file Excel hợp lệ để tạo lịch nháp.")

    upload_recs = [
        {
            "upload_id": u.id,
            "original_name": u.original_name,
            "stored_path": u.stored_path,
            "uploaded_at": u.uploaded_at.isoformat(),
        }
        for u in ups
        if Path(u.stored_path).exists()
    ]
    bundle = extract_workbook_bundle(upload_recs, settings.upload_limits)
    new_ver = ScheduleVersion(
        project_id=project_id,
        version_number=next_num,
        status="draft",
        source_upload_ids_json=json.dumps([u.id for u in ups]),
        created_by=admin.id,
        change_summary=sanitize_user_text(change_summary, 300) or f"Tổng hợp từ {len(ups)} workbook",
    )
    db.add(new_ver)
    db.flush()

    for it in bundle["schedule_items"]:
        db.add(ScheduleItem(
            version_id=new_ver.id,
            date=it["date"],
            class_name=it["class_name"],
            session_type=it["session_type"],
            session_number=it["session_number"],
            start_time=it["start_time"],
            end_time=it["end_time"],
            topic=it["topic"],
            room=it["room"],
            instructor=it["instructor"],
            assistants_json=json.dumps(it["assistants"], ensure_ascii=False),
            room_status=it["room_status"],
            provenance_json=json.dumps(it["provenance"], ensure_ascii=False),
        ))
    db.flush()
    vrun = _run_and_persist_validation(db, new_ver)
    _log_audit(
        db,
        admin,
        "VERSION_CREATE_DRAFT",
        "version",
        new_ver.id,
        {"upload_ids": [u.id for u in ups], "items": len(bundle["schedule_items"])},
    )
    return new_ver, vrun


def _analyze_single_upload_internal(
    db: Session,
    application: FastAPI,
    settings: Settings,
    admin: User,
    up: Upload,
    redact_pii: bool,
) -> dict[str, Any]:
    proj = db.get(Project, up.project_id)
    cfg = _project_cfg(proj) if proj else {}
    ai_enabled = cfg.get("ai_enabled", True)
    budget_usd = float(cfg.get("ai_budget_usd", settings.ai_budget_usd_per_project))

    spent_usd = sum(
        r.estimated_cost
        for r in db.execute(select(AiRun).where(AiRun.project_id == up.project_id)).scalars().all()
    )
    remaining_usd = round(budget_usd - spent_usd, 6)

    pending_rows = db.execute(
        select(MappingDecision).where(
            MappingDecision.upload_id == up.id,
            MappingDecision.admin_decision == "needs_confirmation",
        )
    ).scalars().all()
    mapping_dicts = [
        {"id": m.id, "source_column_or_cell": m.source_column_or_cell, "raw_sample": m.raw_sample}
        for m in pending_rows
    ]

    def _cache_lookup(input_hash: str):
        hit = db.execute(
            select(AiRun).where(
                AiRun.project_id == up.project_id,
                AiRun.input_hash == input_hash,
                AiRun.status == "ok",
            ).order_by(desc(AiRun.id))
        ).scalars().first()
        if not hit:
            return None
        try:
            return json.loads(hit.cached_response_json or "[]")
        except Exception:
            return None

    ai_res = propose_mappings(
        mapping_dicts,
        redact_pii=redact_pii,
        provider_override="disabled" if not ai_enabled else None,
        cached_lookup=_cache_lookup,
        budget_remaining_usd=remaining_usd,
        transport_fn=getattr(application.state, "ai_transport_fn", None),
    )

    db.add(AiRun(
        project_id=up.project_id,
        upload_id=up.id,
        provider=ai_res["provider"],
        model=ai_res["model"],
        prompt_version=ai_res["prompt_version"],
        input_hash=ai_res["input_hash"],
        token_in=ai_res["token_in"],
        token_out=ai_res["token_out"],
        estimated_cost=ai_res["estimated_cost"],
        latency_ms=ai_res["latency_ms"],
        status=ai_res["status"],
        cached_response_json=json.dumps(ai_res["suggestions"], ensure_ascii=False),
    ))

    if ai_res["status"] in ("ok", "cached"):
        by_src = {s["source_column_or_cell"]: s for s in ai_res["suggestions"]}
        for m in pending_rows:
            sugg = by_src.get(m.source_column_or_cell)
            if sugg:
                m.proposed_field = sugg["proposed_field"]
                m.ai_confidence = float(sugg["confidence"])
                m.ai_rationale = sugg["rationale"]
                m.is_mock = ai_res["is_mock"]

    _log_audit(db, admin, "AI_ANALYZE_UPLOAD", "upload", up.id, {
        "provider": ai_res["provider"],
        "status": ai_res["status"],
        "token_in": ai_res["token_in"],
        "token_out": ai_res["token_out"],
        "redact_pii": redact_pii,
    })
    db.flush()
    return ai_res


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    settings = custom_settings or Settings.from_env()
    init_session_factory(settings.database_url)

    application = FastAPI(
        title="AI20K — Trợ lý Tổng hợp & Kiểm tra Lịch Đào tạo (Track A5)",
        version="1.0.0",
        description="API tổng hợp, kiểm tra ràng buộc xác định và duyệt công bố lịch đào tạo từ nhiều file Excel.",
    )
    application.state.settings = settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

    @application.get("/api/health")
    def health():
        ai_cfg = get_ai_config()
        return {
            "status": "ok",
            "ai_provider": ai_cfg["provider"],
            "ai_model": ai_cfg["model"],
            "is_fake_ai": ai_cfg["provider"] == "fake",
        }

    # ============================================================ AUTH

    @application.post("/api/auth/login")
    def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
        client_ip = request.client.host if request.client else "local"
        username = sanitize_user_text(body.username, 80)
        check_rate_limit(client_ip, username)

        user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if not user or not user.active:
            dummy_verify(body.password)
            record_login_failure(client_ip, username)
            _log_audit(db, None, "AUTH_LOGIN_FAILED", "user", username or "unknown", {"reason": "invalid_credentials"})
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Thông tin đăng nhập không hợp lệ.")

        if not verify_password(user.password_hash, body.password):
            record_login_failure(client_ip, username)
            _log_audit(db, user, "AUTH_LOGIN_FAILED", "user", user.id, {"reason": "invalid_credentials"})
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Thông tin đăng nhập không hợp lệ.")

        clear_login_failures(client_ip, username)
        raw_token, csrf_token = create_user_session(db, user, ttl_hours=settings.session_ttl_hours)
        _log_audit(db, user, "AUTH_LOGIN_OK", "user", user.id, {"role": user.role})
        db.commit()

        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=raw_token,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
            max_age=settings.session_ttl_hours * 3600,
            path="/",
        )
        return {
            "user": {"id": user.id, "username": user.username, "role": user.role},
            "csrf_token": csrf_token,
        }

    @application.post("/api/auth/logout")
    def logout(
        response: Response,
        auth_pair: tuple[User, UserSession] = Depends(require_authenticated),
        db: Session = Depends(get_db),
    ):
        user, sess = auth_pair
        sess.revoked_at = utc_now()
        _log_audit(db, user, "AUTH_LOGOUT", "user", user.id, {})
        db.commit()
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return {"ok": True}

    @application.get("/api/auth/me")
    def auth_me(auth_pair: tuple[User, UserSession] = Depends(require_authenticated)):
        user, sess = auth_pair
        return {
            "user": {"id": user.id, "username": user.username, "role": user.role},
            "csrf_token": sess.csrf_token,
        }

    # ============================================================ PROJECTS (Admin only)

    @application.get("/api/projects")
    def list_projects(
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        projects = db.execute(select(Project).order_by(desc(Project.id))).scalars().all()
        out = []
        for p in projects:
            latest_ver = db.execute(
                select(ScheduleVersion).where(ScheduleVersion.project_id == p.id).order_by(desc(ScheduleVersion.version_number))
            ).scalars().first()
            latest_val = _latest_validation_payload(db, latest_ver.id) if latest_ver else None
            out.append({
                "id": p.id,
                "name": p.name,
                "course_code": p.course_code,
                "classes_scope": p.classes_scope,
                "config": _project_cfg(p),
                "active_published_version_id": p.active_published_version_id,
                "latest_version": {
                    "id": latest_ver.id,
                    "version_number": latest_ver.version_number,
                    "status": latest_ver.status,
                    "validation_summary": latest_val["summary"] if latest_val else None,
                } if latest_ver else None,
                "created_at": to_hcm_iso(p.created_at),
            })
        return {"projects": out}

    @application.post("/api/projects", status_code=status.HTTP_201_CREATED)
    def create_project(
        body: ProjectCreateRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        name = sanitize_user_text(body.name, 160)
        if db.execute(select(Project).where(Project.name == name)).scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Tên dự án/khoá học đã tồn tại.")
        cfg = {"ai_enabled": body.ai_enabled, "ai_budget_usd": body.ai_budget_usd}
        proj = Project(
            name=name,
            course_code=sanitize_user_text(body.course_code, 60),
            classes_scope=sanitize_user_text(body.classes_scope, 160),
            config_json=json.dumps(cfg),
            created_by=admin.id,
        )
        db.add(proj)
        db.flush()
        _log_audit(db, admin, "PROJECT_CREATE", "project", proj.id, {"name": name})
        db.commit()
        return {"id": proj.id, "name": proj.name, "course_code": proj.course_code, "classes_scope": proj.classes_scope, "config": cfg}

    @application.patch("/api/projects/{project_id}")
    def update_project(
        project_id: int,
        body: ProjectUpdateRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        cfg = _project_cfg(proj)
        if body.name is not None:
            proj.name = sanitize_user_text(body.name, 160)
        if body.classes_scope is not None:
            proj.classes_scope = sanitize_user_text(body.classes_scope, 160)
        if body.ai_enabled is not None:
            cfg["ai_enabled"] = body.ai_enabled
        if body.ai_budget_usd is not None:
            cfg["ai_budget_usd"] = body.ai_budget_usd
        proj.config_json = json.dumps(cfg)
        _log_audit(db, admin, "PROJECT_UPDATE", "project", proj.id, cfg)
        db.commit()
        return {"id": proj.id, "name": proj.name, "classes_scope": proj.classes_scope, "config": cfg}

    # ============================================================ UPLOADS (Admin only)

    @application.post("/api/projects/{project_id}/uploads")
    async def upload_workbooks(
        project_id: int,
        files: list[UploadFile] = File(...),
        is_synthetic: bool = Query(default=False),
        auto_create_draft: bool = Query(default=False),
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        if not files:
            raise HTTPException(status_code=400, detail="Chưa chọn file Excel nào.")
        if len(files) > settings.upload_limits.max_files_per_batch:
            raise HTTPException(
                status_code=400,
                detail=f"Số file một lần tải ({len(files)}) vượt giới hạn {settings.upload_limits.max_files_per_batch}.",
            )

        accepted_uploads: list[dict[str, Any]] = []
        rejected_reports: list[dict[str, Any]] = []

        for f in files:
            payload = await f.read()
            check = validate_excel_bytes(f.filename, payload, settings.upload_limits)
            if not check["safe"]:
                rejected_reports.append({
                    "original_name": check["safe_display_name"],
                    "status": "rejected",
                    "errors": check["errors"],
                })
                _log_audit(db, admin, "UPLOAD_REJECTED", "upload", check["safe_display_name"], {"errors": check["errors"]})
                continue

            file_id, stored_path = save_safe_upload(settings.upload_dir, payload, check["ext"])
            up = Upload(
                project_id=proj.id,
                file_id=file_id,
                original_name=check["safe_display_name"],
                stored_path=str(stored_path),
                sha256=check["sha256"],
                size_bytes=check["size_bytes"],
                sheet_count=0,
                is_synthetic=is_synthetic or ("synthetic" in check["safe_display_name"].lower()),
                pii_summary_json="{}",
                status="parsed",
                uploaded_by=admin.id,
                uploaded_at=utc_now(),
                error_summary="; ".join(check["warnings"]) if check["warnings"] else None,
            )
            db.add(up)
            db.flush()

            rec = {
                "upload_id": up.id,
                "original_name": up.original_name,
                "stored_path": up.stored_path,
                "uploaded_at": up.uploaded_at.isoformat(),
                "_orm": up,
            }
            bundle = extract_workbook_bundle([rec], settings.upload_limits)
            if bundle["errors"] and not bundle["files"]:
                up.status = "error"
                up.error_summary = "; ".join(e.get("error", "") for e in bundle["errors"])
                rejected_reports.append({
                    "original_name": up.original_name,
                    "status": "error",
                    "errors": [up.error_summary],
                })
                continue

            if bundle["files"]:
                up.sheet_count = len(bundle["files"][0]["sheets"])
            up.pii_summary_json = json.dumps(bundle["pii_summary"], ensure_ascii=False)
            for cell in bundle["extracted_cells"]:
                db.add(SourceCell(**cell))
            for mp in bundle["mapping_candidates"]:
                db.add(MappingDecision(
                    upload_id=up.id,
                    source_column_or_cell=mp["source_column_or_cell"],
                    raw_sample=mp["raw_sample"],
                    proposed_field=mp["proposed_field"],
                    proposed_value_json="{}",
                    ai_confidence=mp["ai_confidence"],
                    ai_rationale=mp["ai_rationale"],
                    is_mock=mp["is_mock"],
                    admin_decision=mp["admin_decision"],
                    final_value_json="{}",
                ))

            accepted_uploads.append({
                "id": up.id,
                "file_id": up.file_id,
                "original_name": up.original_name,
                "sha256": up.sha256,
                "size_bytes": up.size_bytes,
                "sheet_count": up.sheet_count,
                "is_synthetic": up.is_synthetic,
                "pii_summary": bundle["pii_summary"],
                "warnings": check["warnings"],
                "status": up.status,
                "uploaded_at": to_hcm_iso(up.uploaded_at),
            })
            _log_audit(db, admin, "UPLOAD_ACCEPTED", "upload", up.id, {"file_id": up.file_id, "sheet_count": up.sheet_count})

        draft_version_info: dict[str, Any] | None = None
        if auto_create_draft and accepted_uploads:
            db.flush()
            new_ver, vrun = _create_draft_from_uploads_internal(
                db,
                settings,
                admin,
                project_id,
                None,
                f"Tự động tổng hợp sau khi tải lên {len(accepted_uploads)} workbook",
            )
            draft_version_info = {
                "id": new_ver.id,
                "version_number": new_ver.version_number,
                "status": new_ver.status,
                "validation_status": vrun.status,
            }

        db.commit()
        if not accepted_uploads and rejected_reports:
            raise HTTPException(
                status_code=400,
                detail={"message": "Tất cả file tải lên đều không hợp lệ hoặc bị chặn bảo mật.", "rejected": rejected_reports},
            )
        resp: dict[str, Any] = {"accepted": accepted_uploads, "rejected": rejected_reports}
        if draft_version_info is not None:
            resp["draft_version"] = draft_version_info
        return resp

    @application.get("/api/projects/{project_id}/uploads")
    def list_uploads(
        project_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        ups = db.execute(select(Upload).where(Upload.project_id == project_id).order_by(desc(Upload.id))).scalars().all()
        return {
            "uploads": [
                {
                    "id": u.id,
                    "file_id": u.file_id,
                    "original_name": u.original_name,
                    "sha256": u.sha256,
                    "size_bytes": u.size_bytes,
                    "sheet_count": u.sheet_count,
                    "is_synthetic": u.is_synthetic,
                    "pii_summary": json.loads(u.pii_summary_json or "{}"),
                    "status": u.status,
                    "error_summary": u.error_summary,
                    "uploaded_at": to_hcm_iso(u.uploaded_at),
                }
                for u in ups
            ]
        }

    @application.get("/api/uploads/{upload_id}")
    def get_upload(
        upload_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        up = db.get(Upload, upload_id)
        if not up:
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload.")
        return {
            "id": up.id,
            "project_id": up.project_id,
            "file_id": up.file_id,
            "original_name": up.original_name,
            "sha256": up.sha256,
            "size_bytes": up.size_bytes,
            "sheet_count": up.sheet_count,
            "is_synthetic": up.is_synthetic,
            "pii_summary": json.loads(up.pii_summary_json or "{}"),
            "status": up.status,
            "error_summary": up.error_summary,
            "uploaded_at": to_hcm_iso(up.uploaded_at),
        }

    @application.get("/api/uploads/{upload_id}/sheets")
    def get_upload_sheets(
        upload_id: int,
        sheet: str | None = Query(default=None),
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        up = db.get(Upload, upload_id)
        if not up or up.status == "deleted":
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload hoặc file đã bị xoá.")
        cells_q = select(SourceCell).where(SourceCell.upload_id == up.id)
        if sheet:
            cells_q = cells_q.where(SourceCell.sheet == sheet)
        cells = db.execute(cells_q.order_by(SourceCell.id).limit(500)).scalars().all()
        sheet_names = sorted({
            r[0] for r in db.execute(select(SourceCell.sheet).where(SourceCell.upload_id == up.id).distinct()).all()
        })
        if not sheet_names and Path(up.stored_path).exists():
            raw = read_excel_files([up.stored_path])
            if raw.get("files"):
                sheet_names = [s["name"] for s in raw["files"][0]["sheets"]]
        return {
            "upload_id": up.id,
            "original_name": up.original_name,
            "sheets": sheet_names,
            "cells": [
                {
                    "id": c.id,
                    "sheet": c.sheet,
                    "cell_range": c.cell_range,
                    "raw_value": c.raw_value,
                    "normalized_value": c.normalized_value,
                    "sensitivity_flag": c.sensitivity_flag,
                }
                for c in cells
            ],
        }

    @application.delete("/api/uploads/{upload_id}")
    def delete_upload(
        upload_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        up = db.get(Upload, upload_id)
        if not up:
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload.")
        p = Path(up.stored_path)
        if p.exists():
            p.unlink(missing_ok=True)
        up.status = "deleted"
        _log_audit(db, admin, "UPLOAD_DELETE", "upload", up.id, {"file_id": up.file_id})
        db.commit()
        return {"ok": True, "id": up.id, "status": up.status}

    # ============================================================ AI ANALYSIS & MAPPING (Admin only)

    @application.post("/api/uploads/{upload_id}/analyze")
    def analyze_upload_with_ai(
        upload_id: int,
        body: AnalyzeUploadRequest | None = None,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        req_body = body or AnalyzeUploadRequest()
        up = db.get(Upload, upload_id)
        if not up or up.status == "deleted":
            raise HTTPException(status_code=404, detail="Không tìm thấy file upload.")
        ai_res = _analyze_single_upload_internal(db, application, settings, admin, up, req_body.redact_pii)
        db.commit()
        return ai_res

    @application.post("/api/projects/{project_id}/analyze-all")
    def analyze_all_project_uploads(
        project_id: int,
        body: AnalyzeUploadRequest | None = None,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        req_body = body or AnalyzeUploadRequest()
        ups = db.execute(
            select(Upload).where(Upload.project_id == project_id, Upload.status == "parsed").order_by(Upload.id)
        ).scalars().all()
        results: list[dict[str, Any]] = []
        for up in ups:
            has_pending = db.execute(
                select(MappingDecision.id).where(
                    MappingDecision.upload_id == up.id,
                    MappingDecision.admin_decision == "needs_confirmation",
                )
            ).first()
            if not has_pending:
                continue
            res = _analyze_single_upload_internal(db, application, settings, admin, up, req_body.redact_pii)
            results.append({"upload_id": up.id, "original_name": up.original_name, **res})
        db.commit()
        return {"ok": True, "analyzed_uploads": len(results), "results": results}

    @application.get("/api/projects/{project_id}/mappings")
    def list_project_mappings(
        project_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        pairs = db.execute(
            select(MappingDecision, Upload)
            .join(Upload, MappingDecision.upload_id == Upload.id)
            .where(Upload.project_id == project_id, Upload.status == "parsed")
            .order_by(MappingDecision.id)
        ).all()
        sorted_pairs = sorted(pairs, key=lambda x: (0 if x[0].admin_decision == "needs_confirmation" else 1, x[0].id))
        items = [
            {
                "id": m.id,
                "upload_id": m.upload_id,
                "upload_name": u.original_name,
                "source_column_or_cell": m.source_column_or_cell,
                "raw_sample": m.raw_sample,
                "proposed_field": m.proposed_field,
                "ai_confidence": m.ai_confidence,
                "ai_rationale": m.ai_rationale,
                "is_mock": m.is_mock,
                "admin_decision": m.admin_decision,
                "final_value": json.loads(m.final_value_json or "{}"),
                "decided_at": to_hcm_iso(m.decided_at),
            }
            for m, u in sorted_pairs
        ]
        pending_count = sum(1 for m in items if m["admin_decision"] == "needs_confirmation")
        return {"mappings": items, "pending_count": pending_count}

    @application.get("/api/uploads/{upload_id}/mappings")
    def get_upload_mappings(
        upload_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        rows = db.execute(
            select(MappingDecision).where(MappingDecision.upload_id == upload_id).order_by(MappingDecision.id)
        ).scalars().all()
        return {
            "mappings": [
                {
                    "id": m.id,
                    "upload_id": m.upload_id,
                    "source_column_or_cell": m.source_column_or_cell,
                    "raw_sample": m.raw_sample,
                    "proposed_field": m.proposed_field,
                    "ai_confidence": m.ai_confidence,
                    "ai_rationale": m.ai_rationale,
                    "is_mock": m.is_mock,
                    "admin_decision": m.admin_decision,
                    "final_value": json.loads(m.final_value_json or "{}"),
                    "decided_at": to_hcm_iso(m.decided_at),
                }
                for m in rows
            ]
        }

    @application.post("/api/mappings/{mapping_id}/confirm")
    def confirm_mapping(
        mapping_id: int,
        body: MappingConfirmRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        mp = db.get(MappingDecision, mapping_id)
        if not mp:
            raise HTTPException(status_code=404, detail="Không tìm thấy quyết định mapping.")
        mp.admin_decision = body.decision
        chosen_field = sanitize_user_text(body.final_field, 80) if body.final_field else mp.proposed_field
        mp.final_value_json = json.dumps(
            {"field": chosen_field, "note": sanitize_user_text(body.note, 300)}, ensure_ascii=False
        )
        mp.decided_by = admin.id
        mp.decided_at = utc_now()
        _log_audit(db, admin, "MAPPING_CONFIRM", "mapping", mp.id, {"decision": body.decision, "field": chosen_field})
        db.flush()
        up = db.get(Upload, mp.upload_id)
        val_payload = _revalidate_latest_draft_for_project(db, up.project_id) if up else None
        db.commit()
        return {
            "ok": True,
            "id": mp.id,
            "admin_decision": mp.admin_decision,
            "final_value": json.loads(mp.final_value_json),
            "validation": val_payload,
        }

    @application.post("/api/projects/{project_id}/mappings/batch-confirm")
    def batch_confirm_mappings(
        project_id: int,
        body: BatchMappingConfirmRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")
        item_ids = [it.id for it in body.items]
        pairs = db.execute(
            select(MappingDecision)
            .join(Upload, MappingDecision.upload_id == Upload.id)
            .where(Upload.project_id == project_id, MappingDecision.id.in_(item_ids))
        ).scalars().all()
        by_id = {m.id: m for m in pairs}
        updated_count = 0
        now = utc_now()
        for req_item in body.items:
            mp = by_id.get(req_item.id)
            if not mp:
                continue
            mp.admin_decision = req_item.decision
            chosen_field = sanitize_user_text(req_item.final_field, 80) if req_item.final_field else mp.proposed_field
            mp.final_value_json = json.dumps(
                {"field": chosen_field, "note": sanitize_user_text(req_item.note, 300)}, ensure_ascii=False
            )
            mp.decided_by = admin.id
            mp.decided_at = now
            updated_count += 1
        db.flush()
        val_payload = _revalidate_latest_draft_for_project(db, project_id)
        _log_audit(db, admin, "MAPPING_BATCH_CONFIRM", "project", project_id, {"updated_count": updated_count})
        db.commit()
        return {"ok": True, "updated_count": updated_count, "validation": val_payload}

    # ============================================================ VERSIONS, ITEMS, VALIDATION, PUBLISH (Admin)

    @application.get("/api/projects/{project_id}/versions")
    def list_versions(
        project_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        vers = db.execute(
            select(ScheduleVersion).where(ScheduleVersion.project_id == project_id).order_by(desc(ScheduleVersion.version_number))
        ).scalars().all()
        out = []
        for v in vers:
            val = _latest_validation_payload(db, v.id)
            out.append({
                "id": v.id,
                "project_id": v.project_id,
                "version_number": v.version_number,
                "status": v.status,
                "base_version_id": v.base_version_id,
                "source_upload_ids": json.loads(v.source_upload_ids_json or "[]"),
                "created_at": to_hcm_iso(v.created_at),
                "published_at": to_hcm_iso(v.published_at),
                "change_summary": v.change_summary,
                "validation_summary": val["summary"] if val else None,
            })
        return {"versions": out}

    @application.post("/api/projects/{project_id}/versions", status_code=status.HTTP_201_CREATED)
    def create_version_draft(
        project_id: int,
        body: VersionCreateRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        proj = db.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

        existing = db.execute(select(ScheduleVersion).where(ScheduleVersion.project_id == project_id)).scalars().all()
        next_num = (max(v.version_number for v in existing) + 1) if existing else 1

        # Rollback: nhân bản từ một phiên bản cũ thành draft mới, không xoá lịch sử
        if body.from_version_id is not None:
            base_ver = db.get(ScheduleVersion, body.from_version_id)
            if not base_ver or base_ver.project_id != project_id:
                raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản gốc để tạo draft.")
            new_ver = ScheduleVersion(
                project_id=project_id,
                version_number=next_num,
                status="draft",
                base_version_id=base_ver.id,
                source_upload_ids_json=base_ver.source_upload_ids_json,
                created_by=admin.id,
                change_summary=sanitize_user_text(body.change_summary, 300) or f"Rollback / tạo nháp mới từ v{base_ver.version_number}",
            )
            db.add(new_ver)
            db.flush()
            old_items = db.execute(select(ScheduleItem).where(ScheduleItem.version_id == base_ver.id)).scalars().all()
            for oi in old_items:
                db.add(ScheduleItem(
                    version_id=new_ver.id,
                    date=oi.date,
                    class_name=oi.class_name,
                    session_type=oi.session_type,
                    session_number=oi.session_number,
                    start_time=oi.start_time,
                    end_time=oi.end_time,
                    topic=oi.topic,
                    room=oi.room,
                    instructor=oi.instructor,
                    assistants_json=oi.assistants_json,
                    room_status=oi.room_status,
                    provenance_json=oi.provenance_json,
                ))
            db.flush()
            vrun = _run_and_persist_validation(db, new_ver)
            _log_audit(db, admin, "VERSION_ROLLBACK_DRAFT", "version", new_ver.id, {"from_version": base_ver.version_number})
            db.commit()
            return {"id": new_ver.id, "version_number": new_ver.version_number, "status": new_ver.status, "validation_status": vrun.status}

        new_ver, vrun = _create_draft_from_uploads_internal(
            db, settings, admin, project_id, body.upload_ids, body.change_summary
        )
        db.commit()
        return {"id": new_ver.id, "version_number": new_ver.version_number, "status": new_ver.status, "validation_status": vrun.status}

    @application.get("/api/versions/{version_id}")
    def get_version_detail(
        version_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        items = db.execute(
            select(ScheduleItem).where(ScheduleItem.version_id == ver.id).order_by(ScheduleItem.date, ScheduleItem.start_time)
        ).scalars().all()
        return {
            "id": ver.id,
            "project_id": ver.project_id,
            "version_number": ver.version_number,
            "status": ver.status,
            "base_version_id": ver.base_version_id,
            "source_upload_ids": json.loads(ver.source_upload_ids_json or "[]"),
            "created_at": to_hcm_iso(ver.created_at),
            "published_at": to_hcm_iso(ver.published_at),
            "change_summary": ver.change_summary,
            "items": [_serialize_item(x) for x in items],
            "validation": _latest_validation_payload(db, ver.id),
        }

    @application.get("/api/versions/{version_id}/schedule-items")
    def list_schedule_items(
        version_id: int,
        date: str | None = Query(default=None),
        class_name: str | None = Query(default=None),
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        q = select(ScheduleItem).where(ScheduleItem.version_id == version_id)
        if date:
            q = q.where(ScheduleItem.date == sanitize_user_text(date, 20))
        if class_name:
            q = q.where(ScheduleItem.class_name == sanitize_user_text(class_name, 40).upper())
        items = db.execute(q.order_by(ScheduleItem.date, ScheduleItem.start_time)).scalars().all()
        return {"version_id": version_id, "status": ver.status, "items": [_serialize_item(x) for x in items]}

    @application.patch("/api/versions/{version_id}/schedule-items/{item_id}")
    def patch_schedule_item(
        version_id: int,
        item_id: int,
        body: ScheduleItemPatchRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        if ver.status != "draft":
            raise HTTPException(status_code=400, detail="Chỉ được chỉnh sửa phiên bản đang ở trạng thái draft.")
        item = db.get(ScheduleItem, item_id)
        if not item or item.version_id != version_id:
            raise HTTPException(status_code=404, detail="Không tìm thấy buổi học trong phiên bản này.")

        changes: dict[str, Any] = {}
        for field in ("date", "class_name", "start_time", "end_time", "topic", "room", "instructor", "room_status"):
            val = getattr(body, field)
            if val is not None:
                clean_val = sanitize_user_text(val, 255)
                setattr(item, field, clean_val)
                changes[field] = clean_val

        try:
            prov = json.loads(item.provenance_json or "[]")
        except Exception:
            prov = []
        prov.append({
            "manual_override": True,
            "edited_by": admin.username,
            "edited_at": utc_now().isoformat(),
            "reason": sanitize_user_text(body.reason, 240),
            "changes": changes,
        })
        item.provenance_json = json.dumps(prov, ensure_ascii=False)
        db.flush()

        # Tự động chạy lại kiểm tra xác định sau mọi thay đổi
        vrun = _run_and_persist_validation(db, ver)
        _log_audit(db, admin, "SCHEDULE_ITEM_PATCH", "schedule_item", item.id, {"version_id": ver.id, "fields": list(changes.keys())})
        db.commit()
        return {
            "item": _serialize_item(item),
            "validation": _latest_validation_payload(db, ver.id),
            "validation_status": vrun.status,
        }

    @application.post("/api/versions/{version_id}/validate")
    def validate_version_endpoint(
        version_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        vrun = _run_and_persist_validation(db, ver)
        _log_audit(db, admin, "VERSION_VALIDATE", "version", ver.id, {"status": vrun.status})
        db.commit()
        return _latest_validation_payload(db, ver.id)

    @application.get("/api/versions/{version_id}/issues")
    def get_version_issues(
        version_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        payload = _latest_validation_payload(db, ver.id)
        if payload is None:
            _run_and_persist_validation(db, ver)
            db.commit()
            payload = _latest_validation_payload(db, ver.id)
        return payload

    @application.get("/api/versions/{version_id}/announcement-draft")
    def get_announcement_draft(
        version_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        """Sinh bản nháp thông báo có nguồn để Admin copy thủ công (KHÔNG tự gửi ra ngoài)."""
        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")
        items = db.execute(
            select(ScheduleItem).where(ScheduleItem.version_id == ver.id).order_by(ScheduleItem.date, ScheduleItem.start_time)
        ).scalars().all()
        lines = [
            f"[BẢN NHÁP THÔNG BÁO — CHỜ ADMIN DUYỆT & COPY THỦ CÔNG · Phiên bản v{ver.version_number} ({ver.status})]",
            "Hệ thống không tự động gửi tin nhắn ra Discord/Email/Zalo.",
            "",
        ]
        for it in items:
            lines.append(
                f"- {it.date} ({it.start_time}-{it.end_time}) | {it.class_name} {it.session_type} {it.session_number} "
                f"| {it.topic} | Phòng: {it.room or 'chờ XN'} [{it.room_status}] | GV: {it.instructor or 'chưa có'}"
            )
        return {"sent": False, "draft_text": "\n".join(lines)}

    @application.post("/api/versions/{version_id}/publish")
    def publish_version(
        version_id: int,
        body: PublishVersionRequest,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        admin, _ = auth_pair
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Cần xác nhận rõ hành động công bố (confirm=true).")

        ver = db.get(ScheduleVersion, version_id)
        if not ver:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản.")

        # Chống double-submit bằng publish_key
        if body.publish_key:
            dup = db.execute(select(ScheduleVersion).where(ScheduleVersion.publish_key == body.publish_key)).scalar_one_or_none()
            if dup:
                return {
                    "ok": True,
                    "idempotent": True,
                    "version": {"id": dup.id, "version_number": dup.version_number, "status": dup.status, "published_at": to_hcm_iso(dup.published_at)},
                }

        if ver.status == "published":
            return {
                "ok": True,
                "idempotent": True,
                "version": {"id": ver.id, "version_number": ver.version_number, "status": ver.status, "published_at": to_hcm_iso(ver.published_at)},
            }
        if ver.status != "draft":
            raise HTTPException(status_code=400, detail=f"Không thể công bố phiên bản ở trạng thái '{ver.status}'.")

        # Chạy lại validation xác định ngay trước khi công bố trong cùng transaction
        vrun = _run_and_persist_validation(db, ver)
        summary = json.loads(vrun.summary_json or "{}")
        if not summary.get("can_publish"):
            db.commit()  # lưu lại kết quả validation mới nhất để Admin thấy lỗi
            raise HTTPException(
                status_code=400,
                detail=f"CHẶN CÔNG BỐ: còn {summary.get('blocking_count', 1)} lỗi chặn bắt buộc chưa xử lý.",
            )

        proj = db.get(Project, ver.project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

        # Chuyển các bản published cũ của dự án sang superseded (bất biến lịch sử)
        old_pubs = db.execute(
            select(ScheduleVersion).where(
                ScheduleVersion.project_id == proj.id,
                ScheduleVersion.status == "published",
            )
        ).scalars().all()
        for op in old_pubs:
            op.status = "superseded"

        ver.status = "published"
        ver.published_by = admin.id
        ver.published_at = utc_now()
        if body.publish_key:
            ver.publish_key = sanitize_user_text(body.publish_key, 80)
        if body.change_summary:
            ver.change_summary = sanitize_user_text(body.change_summary, 300)
        proj.active_published_version_id = ver.id

        _log_audit(db, admin, "VERSION_PUBLISH", "version", ver.id, {
            "project_id": proj.id,
            "version_number": ver.version_number,
            "warning_count": summary.get("warning_count", 0),
        })
        db.commit()
        return {
            "ok": True,
            "idempotent": False,
            "version": {
                "id": ver.id,
                "version_number": ver.version_number,
                "status": ver.status,
                "published_at": to_hcm_iso(ver.published_at),
            },
        }

    # ============================================================ VIEWER PUBLIC SCHEDULE (Authenticated Viewer or Admin)

    @application.get("/api/public/schedule")
    def get_public_published_schedule(
        project_id: int | None = Query(default=None),
        date: str | None = Query(default=None),
        class_name: str | None = Query(default=None),
        session_type: str | None = Query(default=None),
        auth_pair: tuple[User, UserSession] = Depends(require_authenticated),
        db: Session = Depends(get_db),
    ):
        """Chỉ trả về lịch thuộc phiên bản ĐÃ CÔNG BỐ. Tuyệt đối không trả draft, workbook gốc, PII hoặc audit."""
        proj_q = select(Project).where(Project.active_published_version_id.is_not(None))
        if project_id is not None:
            proj_q = proj_q.where(Project.id == project_id)
        projects = db.execute(proj_q.order_by(desc(Project.id))).scalars().all()
        if not projects:
            return {"projects": [], "active_version": None, "items": []}

        selected_proj = projects[0]
        ver = db.get(ScheduleVersion, selected_proj.active_published_version_id)
        if not ver or ver.status != "published":
            return {"projects": [], "active_version": None, "items": []}

        q = select(ScheduleItem).where(ScheduleItem.version_id == ver.id)
        if date:
            q = q.where(ScheduleItem.date == sanitize_user_text(date, 20))
        if class_name:
            cls_clean = sanitize_user_text(class_name, 20).upper()
            q = q.where(ScheduleItem.class_name.contains(cls_clean))
        if session_type:
            q = q.where(ScheduleItem.session_type == sanitize_user_text(session_type, 20).upper())
        items = db.execute(q.order_by(ScheduleItem.date, ScheduleItem.start_time)).scalars().all()

        return {
            "projects": [{"id": p.id, "name": p.name, "course_code": p.course_code} for p in projects],
            "active_version": {
                "project_id": selected_proj.id,
                "project_name": selected_proj.name,
                "version_number": ver.version_number,
                "published_at": to_hcm_iso(ver.published_at),
            },
            # Chỉ xuất các trường an toàn cho người xem; ẩn provenance file nội bộ & danh sách cá nhân
            "items": [
                {
                    "id": it.id,
                    "date": it.date,
                    "class_name": it.class_name,
                    "session_type": it.session_type,
                    "session_number": it.session_number,
                    "start_time": it.start_time,
                    "end_time": it.end_time,
                    "topic": it.topic,
                    "room": it.room,
                    "instructor": it.instructor,
                    "room_status": it.room_status,
                }
                for it in items
            ],
        }

    # ============================================================ AUDIT & AI RUNS (Admin only)

    @application.get("/api/projects/{project_id}/ai-runs")
    def list_ai_runs(
        project_id: int,
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        runs = db.execute(select(AiRun).where(AiRun.project_id == project_id).order_by(desc(AiRun.id))).scalars().all()
        proj = db.get(Project, project_id)
        cfg = _project_cfg(proj) if proj else {}
        total_cost = round(sum(r.estimated_cost for r in runs), 6)
        return {
            "budget_usd": float(cfg.get("ai_budget_usd", settings.ai_budget_usd_per_project)),
            "total_cost_usd": total_cost,
            "runs": [
                {
                    "id": r.id,
                    "upload_id": r.upload_id,
                    "provider": r.provider,
                    "model": r.model,
                    "prompt_version": r.prompt_version,
                    "input_hash": r.input_hash,
                    "token_in": r.token_in,
                    "token_out": r.token_out,
                    "estimated_cost": r.estimated_cost,
                    "latency_ms": r.latency_ms,
                    "status": r.status,
                    "created_at": to_hcm_iso(r.created_at),
                }
                for r in runs
            ],
        }

    @application.get("/api/audit")
    def list_audit_logs(
        limit: int = Query(default=100, ge=1, le=500),
        auth_pair: tuple[User, UserSession] = Depends(require_admin),
        db: Session = Depends(get_db),
    ):
        logs = db.execute(select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)).scalars().all()
        return {
            "logs": [
                {
                    "id": lg.id,
                    "actor_username": lg.actor_username,
                    "action": lg.action,
                    "entity_type": lg.entity_type,
                    "entity_id": lg.entity_id,
                    "timestamp": to_hcm_iso(lg.timestamp),
                    "metadata": json.loads(lg.safe_metadata_json or "{}"),
                }
                for lg in logs
            ]
        }

    return application


app = create_app()
