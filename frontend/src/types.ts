export interface UserInfo {
  id: number;
  username: string;
  role: "admin" | "viewer";
}

export interface HealthInfo {
  status: string;
  ai_provider: string;
  ai_model: string;
  is_fake_ai: boolean;
}

export interface ValidationSummary {
  can_publish: boolean;
  blocking_count: number;
  warning_count: number;
  total_items: number;
  rule_statuses?: {
    rule_id: string;
    title: string;
    status: "pass" | "warning" | "blocking";
    issue_count: number;
  }[];
}

export interface ProjectSummary {
  id: number;
  name: string;
  course_code: string;
  classes_scope: string;
  config: { ai_enabled?: boolean; ai_budget_usd?: number };
  active_published_version_id: number | null;
  latest_version: {
    id: number;
    version_number: number;
    status: string;
    validation_summary: ValidationSummary | null;
  } | null;
  created_at: string | null;
}

export interface UploadRecord {
  id: number;
  file_id: string;
  original_name: string;
  sha256: string;
  size_bytes: number;
  sheet_count: number;
  is_synthetic: boolean;
  pii_summary: { total_sensitive_cells?: number; by_flag?: Record<string, number> };
  warnings?: string[];
  status: string;
  error_summary?: string | null;
  uploaded_at: string | null;
}

export interface SourceCellRecord {
  id: number;
  sheet: string;
  cell_range: string;
  raw_value: string;
  normalized_value: string;
  sensitivity_flag: string;
}

export interface MappingRecord {
  id: number;
  upload_id: number;
  upload_name?: string;
  source_column_or_cell: string;
  raw_sample: string;
  proposed_field: string | null;
  ai_confidence: number;
  ai_rationale: string;
  is_mock: boolean;
  admin_decision: "needs_confirmation" | "accepted" | "edited" | "rejected";
  final_value: { field?: string; note?: string };
  decided_at: string | null;
}

export type AdminWorkspaceId = "ingest" | "workbench" | "publish" | "history" | "viewer_preview";

export interface SourceInspectTarget {
  uploadId: number;
  sheet?: string;
  highlightCell?: string;
}

export interface ProvenanceEntry {
  file?: string;
  sheet?: string;
  cell_range?: string;
  source_cell?: string;
  upload_id?: number;
  uploaded_at?: string;
  source_timestamp?: string;
  manual_override?: boolean;
  edited_by?: string;
  edited_at?: string;
  reason?: string;
}

export interface ScheduleItemRecord {
  id: number;
  version_id: number;
  date: string;
  class_name: string;
  session_type: string;
  session_number: number;
  start_time: string;
  end_time: string;
  topic: string;
  room: string;
  instructor: string;
  assistants: string[];
  room_status: "confirmed" | "tentative" | "pending" | "online";
  provenance: ProvenanceEntry[];
}

export interface ValidationIssueRecord {
  id: number;
  rule_id: string;
  severity: "blocking" | "warning" | "info";
  message: string;
  remediation: string;
  affected_items: string[];
  provenance: unknown[];
  resolved_status: string;
}

export interface ValidationPayload {
  id: number;
  version_id: number;
  ruleset_version: string;
  status: "passed" | "blocked";
  finished_at: string | null;
  summary: ValidationSummary;
  issues: ValidationIssueRecord[];
}

export interface VersionDetail {
  id: number;
  project_id: number;
  version_number: number;
  status: "draft" | "published" | "superseded";
  base_version_id: number | null;
  source_upload_ids: number[];
  created_at: string | null;
  published_at: string | null;
  change_summary: string | null;
  items: ScheduleItemRecord[];
  validation: ValidationPayload | null;
}

export interface AiRunRecord {
  id: number;
  upload_id: number | null;
  provider: string;
  model: string;
  prompt_version: string;
  input_hash: string;
  token_in: number;
  token_out: number;
  estimated_cost: number;
  latency_ms: number;
  status: string;
  created_at: string | null;
}

export interface AuditLogRecord {
  id: number;
  actor_username: string;
  action: string;
  entity_type: string;
  entity_id: string;
  timestamp: string | null;
  metadata: Record<string, unknown>;
}
