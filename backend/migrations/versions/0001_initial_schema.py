"""Initial schema for AI20K Track A5 training schedule assistant

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("course_code", sa.String(length=60), nullable=False),
        sa.Column("classes_scope", sa.String(length=160), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("active_published_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sheet_count", sa.Integer(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("pii_summary_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id"),
    )
    op.create_index("ix_uploads_project_id", "uploads", ["project_id"], unique=False)
    op.create_index("ix_uploads_sha256", "uploads", ["sha256"], unique=False)

    op.create_table(
        "source_cells",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("workbook", sa.String(length=255), nullable=False),
        sa.Column("sheet", sa.String(length=160), nullable=False),
        sa.Column("cell_range", sa.String(length=40), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("sensitivity_flag", sa.String(length=60), nullable=False),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_cells_upload_id", "source_cells", ["upload_id"], unique=False)
    op.create_index("ix_source_cells_upload_sheet", "source_cells", ["upload_id", "sheet"], unique=False)

    op.create_table(
        "schedule_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("source_upload_ids_json", sa.Text(), nullable=False),
        sa.Column("publish_key", sa.String(length=80), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version_number", name="uq_project_version_number"),
        sa.UniqueConstraint("publish_key"),
    )
    op.create_index("ix_schedule_versions_project_id", "schedule_versions", ["project_id"], unique=False)
    op.create_index("ix_schedule_versions_status", "schedule_versions", ["status"], unique=False)

    op.create_table(
        "schedule_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("class_name", sa.String(length=40), nullable=False),
        sa.Column("session_type", sa.String(length=20), nullable=False),
        sa.Column("session_number", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(length=10), nullable=False),
        sa.Column("end_time", sa.String(length=10), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("room", sa.String(length=160), nullable=False),
        sa.Column("instructor", sa.String(length=160), nullable=False),
        sa.Column("assistants_json", sa.Text(), nullable=False),
        sa.Column("room_status", sa.String(length=30), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["schedule_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedule_items_class_name", "schedule_items", ["class_name"], unique=False)
    op.create_index("ix_schedule_items_date", "schedule_items", ["date"], unique=False)
    op.create_index("ix_schedule_items_ver_date_cls", "schedule_items", ["version_id", "date", "class_name"], unique=False)
    op.create_index("ix_schedule_items_version_id", "schedule_items", ["version_id"], unique=False)

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["schedule_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_runs_version_id", "validation_runs", ["version_id"], unique=False)

    op.create_table(
        "validation_issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("validation_run_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("remediation", sa.Text(), nullable=False),
        sa.Column("affected_items_json", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("resolved_status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["validation_run_id"], ["validation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_issues_rule_id", "validation_issues", ["rule_id"], unique=False)
    op.create_index("ix_validation_issues_severity", "validation_issues", ["severity"], unique=False)
    op.create_index("ix_validation_issues_validation_run_id", "validation_issues", ["validation_run_id"], unique=False)

    op.create_table(
        "mapping_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("source_column_or_cell", sa.String(length=255), nullable=False),
        sa.Column("raw_sample", sa.Text(), nullable=False),
        sa.Column("proposed_field", sa.String(length=80), nullable=True),
        sa.Column("proposed_value_json", sa.Text(), nullable=False),
        sa.Column("ai_confidence", sa.Float(), nullable=False),
        sa.Column("ai_rationale", sa.Text(), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("admin_decision", sa.String(length=30), nullable=False),
        sa.Column("final_value_json", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mapping_decisions_admin_decision", "mapping_decisions", ["admin_decision"], unique=False)
    op.create_index("ix_mapping_decisions_upload_id", "mapping_decisions", ["upload_id"], unique=False)

    op.create_table(
        "ai_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("upload_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=False),
        sa.Column("token_out", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cached_response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_runs_input_hash", "ai_runs", ["input_hash"], unique=False)
    op.create_index("ix_ai_runs_project_id", "ai_runs", ["project_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=60), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("safe_metadata_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"], unique=False)
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("ai_runs")
    op.drop_table("mapping_decisions")
    op.drop_table("validation_issues")
    op.drop_table("validation_runs")
    op.drop_table("schedule_items")
    op.drop_table("schedule_versions")
    op.drop_table("source_cells")
    op.drop_table("uploads")
    op.drop_table("projects")
    op.drop_table("user_sessions")
    op.drop_table("users")
