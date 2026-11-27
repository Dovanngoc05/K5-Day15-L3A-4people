import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type {
  AdminWorkspaceId,
  AiRunRecord,
  AuditLogRecord,
  HealthInfo,
  MappingRecord,
  ProjectSummary,
  ScheduleItemRecord,
  SourceCellRecord,
  SourceInspectTarget,
  UploadRecord,
  ValidationIssueRecord,
  VersionDetail,
} from "../types";
import { ViewerView } from "./ViewerView";

export interface VersionListItem {
  id: number;
  version_number: number;
  status: string;
  created_at: string | null;
  published_at: string | null;
  change_summary: string | null;
}

const STANDARD_FIELDS = [
  { value: "", label: "-- Không gán / Bỏ qua --" },
  { value: "date", label: "date (Ngày học)" },
  { value: "class_name", label: "class_name (Lớp)" },
  { value: "session", label: "session (Buổi LEC/LAB)" },
  { value: "start_time", label: "start_time (Giờ BĐ)" },
  { value: "end_time", label: "end_time (Giờ KT)" },
  { value: "topic", label: "topic (Chủ đề)" },
  { value: "room", label: "room (Phòng học)" },
  { value: "instructor", label: "instructor (Giảng viên)" },
  { value: "assistants", label: "assistants (Coach / TG)" },
  { value: "notes", label: "notes (Ghi chú)" },
];

export function SeverityBadge({ severity }: { severity: string }) {
  if (severity === "blocking") return <span className="badge badge-err">✖ [LỖI CHẶN]</span>;
  if (severity === "warning") return <span className="badge badge-wrn">⚠ [CẢNH BÁO]</span>;
  if (severity === "pass") return <span className="badge badge-ok">✔ [ĐẠT]</span>;
  return <span className="badge badge-inf">ℹ [THÔNG TIN]</span>;
}

function doesIssueAffectItem(it: ScheduleItemRecord, iss: ValidationIssueRecord): boolean {
  const label = `${it.class_name} ${it.session_type} ${it.session_number}`.toLowerCase();
  const fullKey = `${label} (${it.date})`.toLowerCase();
  return iss.affected_items.some((ref) => {
    const r = String(ref).toLowerCase();
    return r === String(it.id) || r === label || r === fullKey || (r.includes(label) && (!r.includes("(") || r.includes(it.date)));
  });
}

function extractSearchToken(rawCell?: string): string {
  if (!rawCell) return "";
  const m = rawCell.match(/[A-Z]+\d+/i);
  return m ? m[0] : rawCell;
}

/* ============================================================================
 * NGĂN TRƯỢT XEM NHANH Ô NGUỒN EXCEL (SOURCE INSPECTOR DRAWER)
 * ========================================================================== */
export function SourceInspectorDrawer({
  target,
  uploads,
  onClose,
}: {
  target: SourceInspectTarget | null;
  uploads: UploadRecord[];
  onClose: () => void;
}) {
  const [uploadId, setUploadId] = useState<number>(0);
  const [sheets, setSheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>("");
  const [cells, setCells] = useState<SourceCellRecord[]>([]);
  const [cellFilter, setCellFilter] = useState<string>("");
  const [onlySensitive, setOnlySensitive] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [err, setErr] = useState<string>("");

  async function fetchSheetData(uId: number, shName: string) {
    if (!uId) return;
    setLoading(true);
    setErr("");
    try {
      const qs = shName ? `?sheet=${encodeURIComponent(shName)}` : "";
      const res = await api.get<{ sheets: string[]; cells: SourceCellRecord[] }>(`/api/uploads/${uId}/sheets${qs}`);
      setSheets(res.sheets);
      setCells(res.cells);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Không tải được dữ liệu ô nguồn.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!target) return;
    setUploadId(target.uploadId);
    const sh = target.sheet || "";
    setSelectedSheet(sh);
    setCellFilter(extractSearchToken(target.highlightCell));
    setOnlySensitive(false);
    void fetchSheetData(target.uploadId, sh);
  }, [target]);

  const visibleCells = useMemo(() => {
    const q = cellFilter.trim().toLowerCase();
    return cells.filter((c) => {
      if (onlySensitive && c.sensitivity_flag === "normal") return false;
      if (!q) return true;
      return (
        c.cell_range.toLowerCase().includes(q) ||
        c.raw_value.toLowerCase().includes(q) ||
        c.sheet.toLowerCase().includes(q)
      );
    });
  }, [cells, cellFilter, onlySensitive]);

  if (!target) return null;

  const parsedUploads = uploads.filter((u) => u.status === "parsed");

  return (
    <div
      className="drawer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Đối chiếu ô nguồn Excel"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="drawer-panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h3 style={{ margin: 0 }}>🔍 Đối chiếu ô nguồn Excel (Provenance)</h3>
            <div className="sub">Dữ liệu gốc lưu chỉ đọc kèm toạ độ ô và gắn cờ PII</div>
          </div>
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            ✕ Đóng (Esc)
          </button>
        </div>

        <div className="grid2">
          <div>
            <label htmlFor="drw-up">Workbook</label>
            <select
              id="drw-up"
              value={uploadId}
              onChange={(e) => {
                const nextId = Number(e.target.value);
                setUploadId(nextId);
                setSelectedSheet("");
                setCellFilter("");
                void fetchSheetData(nextId, "");
              }}
            >
              {parsedUploads.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.original_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="drw-sh">Sheet</label>
            <select
              id="drw-sh"
              value={selectedSheet}
              onChange={(e) => {
                const nextSh = e.target.value;
                setSelectedSheet(nextSh);
                void fetchSheetData(uploadId, nextSh);
              }}
            >
              <option value="">Tất cả sheet ({sheets.length})</option>
              {sheets.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="row">
          <div style={{ flex: 1, minWidth: 180 }}>
            <input
              aria-label="Tìm nhanh theo ô hoặc giá trị"
              value={cellFilter}
              onChange={(e) => setCellFilter(e.target.value)}
              placeholder="Tìm toạ độ ô (vd: F6) hoặc nội dung…"
            />
          </div>
          {cellFilter && (
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setCellFilter("")}>
              Hiện cả sheet
            </button>
          )}
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, width: "auto", margin: 0 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={onlySensitive}
              onChange={(e) => setOnlySensitive(e.target.checked)}
            />
            Chỉ ô PII/Cảnh báo
          </label>
        </div>

        {err && <div className="banner banner-err">[LỖI] {err}</div>}
        {loading && <div className="banner banner-inf">Đang tải dữ liệu ô nguồn…</div>}

        <div className="sub">
          Hiển thị <strong>{visibleCells.length}</strong> / {cells.length} ô (tối đa 500 ô/truy vấn)
        </div>

        <div className="table-wrap" style={{ flex: 1, maxHeight: "none" }}>
          <table>
            <thead>
              <tr>
                <th>Sheet</th>
                <th>Toạ độ ô</th>
                <th>Giá trị thô</th>
                <th>Độ nhạy</th>
              </tr>
            </thead>
            <tbody>
              {visibleCells.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", padding: 20 }}>
                    Không có ô nào khớp bộ lọc.
                  </td>
                </tr>
              ) : (
                visibleCells.map((c) => (
                  <tr
                    key={c.id}
                    className={cellFilter && c.cell_range.toLowerCase().includes(cellFilter.toLowerCase()) ? "row-highlight" : "row-hover"}
                  >
                    <td><strong>{c.sheet}</strong></td>
                    <td><code>{c.cell_range}</code></td>
                    <td style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{c.raw_value}</td>
                    <td>
                      <span className={`badge ${c.sensitivity_flag === "normal" ? "badge-ok" : "badge-wrn"}`}>
                        [{c.sensitivity_flag}]
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ============================================================================
 * BƯỚC 1: NHẬP EXCEL 1 CHẠM & XÁC NHẬN MAPPING TOÀN DỰ ÁN
 * ========================================================================== */
export function IngestWorkspace({
  project,
  health,
  uploads,
  mappings,
  onUploaded,
  onMappingsChanged,
  onCreateDraftFromUploads,
  onInspectSource,
  onGoWorkbench,
}: {
  project: ProjectSummary | null;
  health: HealthInfo | null;
  uploads: UploadRecord[];
  mappings: MappingRecord[];
  onUploaded: (createdDraftId?: number, autoGoToWorkbench?: boolean) => Promise<void>;
  onMappingsChanged: () => Promise<void>;
  onCreateDraftFromUploads: (uploadIds: number[]) => Promise<void>;
  onInspectSource: (target: SourceInspectTarget) => void;
  onGoWorkbench: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [drag, setDrag] = useState(false);
  const [autoDraft, setAutoDraft] = useState(true);
  const [busyUpload, setBusyUpload] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  // State cho Mapping & AI
  const [mapFilter, setMapFilter] = useState<"pending" | "all">("pending");
  const [uploadFilter, setUploadFilter] = useState<number>(0);
  const [redactPii, setRedactPii] = useState(true);
  const [aiBusy, setAiBusy] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [mapMsg, setMapMsg] = useState("");
  const [mapErr, setMapErr] = useState("");
  const [editFields, setEditFields] = useState<Record<number, string>>({});

  if (!project) return <div className="banner banner-wrn">Hãy chọn hoặc tạo dự án trước ở thanh trên cùng.</div>;

  const parsedUploads = uploads.filter((u) => u.status === "parsed");
  const hasSynthetic = uploads.some((u) => u.is_synthetic);

  const pendingMappings = mappings.filter((m) => m.admin_decision === "needs_confirmation");
  const pendingWithField = pendingMappings.filter((m) => Boolean(m.proposed_field));
  const pendingWithoutField = pendingMappings.filter((m) => !m.proposed_field);

  const visibleMappings = mappings.filter((m) => {
    if (mapFilter === "pending" && m.admin_decision !== "needs_confirmation") return false;
    if (uploadFilter && m.upload_id !== uploadFilter) return false;
    return true;
  });

  async function handleUpload() {
    if (!project || files.length === 0) return;
    setBusyUpload(true);
    setErr("");
    setMsg("");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const res = await api.upload<{
        accepted: UploadRecord[];
        rejected: { original_name: string; errors: string[] }[];
        draft_version?: { id: number; version_number: number; validation_status: string } | null;
      }>(`/api/projects/${project.id}/uploads?auto_create_draft=${autoDraft ? "true" : "false"}`, fd);

      setFiles([]);
      let nextPending = 0;
      if (res.draft_version && res.rejected.length === 0) {
        const mCheck = await api.get<{ pending_count: number }>(`/api/projects/${project.id}/mappings`);
        nextPending = mCheck.pending_count;
      }

      const okTxt = `Đã lưu & kiểm tra an toàn ${res.accepted.length} file.`;
      const rejTxt = res.rejected.length
        ? ` Bị từ chối ${res.rejected.length} file: ${res.rejected.map((r) => `${r.original_name} (${r.errors.join("; ")})`).join(" | ")}.`
        : "";
      const draftTxt = res.draft_version
        ? ` Đã tự động tổng hợp Draft v${res.draft_version.version_number}${nextPending > 0 ? ` (còn ${nextPending} mục cần xác nhận bên dưới)` : ""}.`
        : "";

      setMsg(okTxt + draftTxt + rejTxt);

      const shouldAutoJump = Boolean(res.draft_version && res.rejected.length === 0 && nextPending === 0);
      await onUploaded(res.draft_version?.id, shouldAutoJump);

      if (res.draft_version && nextPending > 0) {
        document.getElementById("mapping-section")?.scrollIntoView({ behavior: "smooth" });
      }
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Upload thất bại.");
    } finally {
      setBusyUpload(false);
    }
  }

  async function handleDelete(id: number) {
    setErr("");
    try {
      await api.del(`/api/uploads/${id}`);
      await onUploaded();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Không thể xoá file.");
    }
  }

  async function runAnalyzeAll() {
    if (!project) return;
    setAiBusy(true);
    setMapErr("");
    setMapMsg("");
    try {
      const res = await api.post<{
        ok: boolean;
        analyzed_uploads: number;
        results: { original_name: string; status: string; provider: string; token_in: number; token_out: number; message: string }[];
      }>(`/api/projects/${project.id}/analyze-all`, { redact_pii: redactPii });
      if (res.analyzed_uploads === 0) {
        setMapMsg("Không có cột/ô nào đang ở trạng thái chờ xác nhận.");
      } else {
        const summary = res.results
          .map((r) => `${r.original_name}: ${r.status} (${r.provider}, ${r.token_in}/${r.token_out} token)`)
          .join(" · ");
        setMapMsg(`Hoàn tất đề xuất AI cho ${res.analyzed_uploads} workbook: ${summary}`);
      }
      await onMappingsChanged();
    } catch (ex) {
      setMapErr(ex instanceof Error ? ex.message : "Gọi AI phân tích thất bại.");
    } finally {
      setAiBusy(false);
    }
  }

  async function confirmSingleMapping(m: MappingRecord, decision: "accepted" | "edited" | "rejected") {
    setMapErr("");
    setMapMsg("");
    try {
      const chosen = decision === "edited" ? editFields[m.id] ?? m.proposed_field ?? "" : m.proposed_field;
      await api.post(`/api/mappings/${m.id}/confirm`, {
        decision,
        final_field: chosen || null,
        note: "Admin xác nhận tại Bước 1",
      });
      await onMappingsChanged();
    } catch (ex) {
      setMapErr(ex instanceof Error ? ex.message : "Xác nhận thất bại.");
    }
  }

  async function batchConfirm(targetItems: MappingRecord[], decision: "accepted" | "rejected", note: string) {
    if (!project || targetItems.length === 0) return;
    setBatchBusy(true);
    setMapErr("");
    setMapMsg("");
    try {
      const payload = {
        items: targetItems.map((m) => ({
          id: m.id,
          decision,
          final_field: decision === "accepted" ? m.proposed_field : null,
          note,
        })),
      };
      const res = await api.post<{ ok: boolean; updated_count: number }>(`/api/projects/${project.id}/mappings/batch-confirm`, payload);
      setMapMsg(`Đã xử lý hàng loạt ${res.updated_count} mục mapping (${decision}) và tự động kiểm tra lại Draft.`);
      await onMappingsChanged();
    } catch (ex) {
      setMapErr(ex instanceof Error ? ex.message : "Xử lý hàng loạt thất bại.");
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <div>
      {health?.is_fake_ai && (
        <div className="banner banner-wrn">
          ⚠ <strong>[CHẾ ĐỘ AI GIẢ LẬP — OFFLINE]</strong> Hiện <code>AI_PROVIDER=fake</code>. Các đề xuất chuẩn hoá chạy cục bộ không tốn chi phí và luôn gắn nhãn giả lập.
        </div>
      )}
      {hasSynthetic && (
        <div className="banner banner-inf">
          ℹ <strong>[DỮ LIỆU GIẢ LẬP / SYNTHETIC]</strong> Dự án đang chứa workbook synthetic để kiểm thử vận hành.
        </div>
      )}

      {/* KHUNG 1: UPLOAD NHANH */}
      <section className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <h2 style={{ margin: 0 }}>Bước 1 · Nhập Workbook Excel &amp; Tạo Lịch Nháp</h2>
            <div className="sub">
              Hỗ trợ tải nhiều file <code>.xlsx</code> cùng lúc (tối đa 10 MB/file · chặn macro VBA, ActiveX, XXE, ZIP bomb).
            </div>
          </div>
          {parsedUploads.length > 0 && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => onCreateDraftFromUploads(selectedIds.length ? selectedIds : parsedUploads.map((u) => u.id))}
            >
              ↻ Tổng hợp lại Draft ({selectedIds.length || parsedUploads.length} file)
            </button>
          )}
        </div>

        <div
          className={`dropzone ${drag ? "drag" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            if (e.dataTransfer.files?.length) setFiles(Array.from(e.dataTransfer.files));
          }}
        >
          <label htmlFor="up-file" style={{ cursor: "pointer", fontSize: 14, color: "var(--text)" }}>
            <strong>Kéo thả nhiều file Excel (.xlsx) vào đây hoặc bấm để chọn</strong>
          </label>
          <input
            id="up-file"
            type="file"
            multiple
            accept=".xlsx,.xlsm"
            style={{ marginTop: 8, maxWidth: 420 }}
            onChange={(e) => setFiles(e.target.files ? Array.from(e.target.files) : [])}
          />
          {files.length > 0 && (
            <div style={{ marginTop: 8 }}>
              Đã chọn <strong>{files.length}</strong> file: {files.map((f) => f.name).join(", ")}
            </div>
          )}
        </div>

        <div className="row" style={{ justifyContent: "space-between", marginTop: 12 }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, width: "auto", margin: 0, cursor: "pointer" }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={autoDraft}
              onChange={(e) => setAutoDraft(e.target.checked)}
            />
            <span>Tự động tổng hợp thành Lịch nháp &amp; chạy kiểm tra ngay sau khi tải lên</span>
          </label>
          <button type="button" className="btn btn-primary" disabled={busyUpload || files.length === 0} onClick={handleUpload}>
            {busyUpload
              ? "Đang quét an toàn & tổng hợp…"
              : autoDraft
                ? "⚡ Tải lên & Tạo Lịch nháp ngay"
                : "Tải lên & Kiểm tra an toàn"}
          </button>
        </div>

        {msg && <div className="banner banner-ok" style={{ marginTop: 10 }}>[KẾT QUẢ] {msg}</div>}
        {err && <div className="banner banner-err" style={{ marginTop: 10 }}>[BỊ CHẶN / LỖI] {err}</div>}

        {uploads.length > 0 && (
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table>
              <thead>
                <tr>
                  <th>Chọn</th>
                  <th>Workbook</th>
                  <th>Trạng thái</th>
                  <th>Sheets</th>
                  <th>PII / Ghi chú</th>
                  <th>Thao tác nhanh</th>
                </tr>
              </thead>
              <tbody>
                {uploads.map((u) => (
                  <tr key={u.id} className="row-hover">
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Chọn ${u.original_name}`}
                        style={{ width: "auto" }}
                        disabled={u.status !== "parsed"}
                        checked={selectedIds.includes(u.id)}
                        onChange={() =>
                          setSelectedIds((prev) => (prev.includes(u.id) ? prev.filter((x) => x !== u.id) : [...prev, u.id]))
                        }
                      />
                    </td>
                    <td>
                      <strong>{u.original_name}</strong>
                      <div className="sub">{Math.round(u.size_bytes / 1024)} KB · {u.uploaded_at}</div>
                    </td>
                    <td>
                      <span className={`badge ${u.status === "parsed" ? "badge-ok" : "badge-err"}`}>[{u.status}]</span>
                    </td>
                    <td>{u.sheet_count}</td>
                    <td>
                      {u.is_synthetic && <span className="badge badge-inf">[SYNTHETIC]</span>}{" "}
                      {(u.pii_summary?.total_sensitive_cells ?? 0) > 0 && (
                        <span className="badge badge-wrn">[PII: {u.pii_summary.total_sensitive_cells} ô]</span>
                      )}
                      {u.error_summary && <div className="sub">{u.error_summary}</div>}
                    </td>
                    <td>
                      <div className="row">
                        {u.status === "parsed" && (
                          <button
                            type="button"
                            className="btn btn-sm btn-ghost"
                            onClick={() => onInspectSource({ uploadId: u.id })}
                          >
                            🔍 Xem ô nguồn
                          </button>
                        )}
                        {u.status !== "deleted" && (
                          <button type="button" className="btn btn-sm btn-danger" onClick={() => void handleDelete(u.id)}>
                            Xoá
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* KHUNG 2: XÁC NHẬN MAPPING & ĐỀ XUẤT AI TOÀN DỰ ÁN */}
      <section id="mapping-section" className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <h3 style={{ margin: 0 }}>
              Chuẩn hoá cột &amp; ô mơ hồ{" "}
              {pendingMappings.length > 0 ? (
                <span className="badge badge-wrn">Còn {pendingMappings.length} mục chờ xác nhận</span>
              ) : (
                <span className="badge badge-ok">✔ Sạch mục chờ</span>
              )}
            </h3>
            <div className="sub">
              Danh sách tự động tổng hợp từ tất cả workbook của dự án. Xác nhận xong hệ thống tự kiểm tra lại <code>HC-MAPPING-PENDING</code>.
            </div>
          </div>
          <div className="row">
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, width: "auto", margin: 0 }}>
              <input type="checkbox" style={{ width: "auto" }} checked={redactPii} onChange={(e) => setRedactPii(e.target.checked)} />
              Ẩn danh PII trước khi gửi AI
            </label>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={aiBusy || pendingMappings.length === 0}
              onClick={runAnalyzeAll}
            >
              {aiBusy ? "Đang phân tích…" : `🤖 Đề xuất AI cho tất cả ô chờ (${pendingMappings.length})`}
            </button>
          </div>
        </div>

        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div className="pill-group">
            <button
              type="button"
              className={`pill-btn ${mapFilter === "pending" ? "active" : ""}`}
              onClick={() => setMapFilter("pending")}
            >
              Chờ xác nhận ({pendingMappings.length})
            </button>
            <button
              type="button"
              className={`pill-btn ${mapFilter === "all" ? "active" : ""}`}
              onClick={() => setMapFilter("all")}
            >
              Tất cả ({mappings.length})
            </button>
            {parsedUploads.length > 1 && (
              <select
                aria-label="Lọc theo workbook"
                style={{ width: "auto", padding: "4px 8px", fontSize: 12 }}
                value={uploadFilter}
                onChange={(e) => setUploadFilter(Number(e.target.value))}
              >
                <option value={0}>Tất cả workbook</option>
                {parsedUploads.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.original_name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {pendingMappings.length > 0 && (
            <div className="row">
              {pendingWithField.length > 0 && (
                <button
                  type="button"
                  className="btn btn-sm btn-success"
                  disabled={batchBusy}
                  onClick={() => void batchConfirm(pendingWithField, "accepted", "Admin duyệt hàng loạt đề xuất hợp lệ")}
                >
                  ✔ Chấp nhận tất cả đề xuất hợp lệ ({pendingWithField.length})
                </button>
              )}
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                disabled={batchBusy}
                onClick={() =>
                  void batchConfirm(
                    pendingWithoutField.length > 0 ? pendingWithoutField : pendingMappings,
                    "rejected",
                    "Admin bỏ qua cột ghi chú phụ",
                  )
                }
              >
                ✖ Bỏ qua {pendingWithoutField.length > 0 ? `các mục chưa rõ (${pendingWithoutField.length})` : `tất cả đang chờ (${pendingMappings.length})`}
              </button>
            </div>
          )}
        </div>

        {mapMsg && <div className="banner banner-inf">[AI / MAPPING] {mapMsg}</div>}
        {mapErr && <div className="banner banner-err">[LỖI] {mapErr}</div>}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nguồn (File :: Sheet :: Ô)</th>
                <th>Mẫu dữ liệu</th>
                <th>Đề xuất &amp; Căn cứ</th>
                <th>Trạng thái</th>
                <th>Chọn trường &amp; Xác nhận nhanh</th>
              </tr>
            </thead>
            <tbody>
              {visibleMappings.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: "center", padding: 18 }}>
                    {pendingMappings.length === 0
                      ? "Tất cả mapping đã được xử lý xong! Bạn có thể sang Bước 2 ngay."
                      : "Không có mục nào khớp bộ lọc."}
                  </td>
                </tr>
              ) : (
                visibleMappings.map((m) => (
                  <tr key={m.id} className="row-hover">
                    <td>
                      <code>{m.source_column_or_cell}</code>
                      {m.upload_name && <div className="sub">📄 {m.upload_name}</div>}
                    </td>
                    <td style={{ maxWidth: 220, wordBreak: "break-word" }}>{m.raw_sample || "—"}</td>
                    <td>
                      <span className="badge badge-inf">
                        {m.is_mock ? "[Giả lập]" : "[AI]"} {m.proposed_field || "Chưa rõ"} ({Math.round(m.ai_confidence * 100)}%)
                      </span>
                      <div className="sub" style={{ marginTop: 4 }}>{m.ai_rationale}</div>
                    </td>
                    <td>
                      <span className={`badge ${m.admin_decision === "needs_confirmation" ? "badge-wrn" : "badge-ok"}`}>
                        [{m.admin_decision}]
                      </span>
                      {m.final_value?.field && <div className="sub">Đã chốt: <b>{m.final_value.field}</b></div>}
                    </td>
                    <td>
                      <div className="row">
                        <select
                          aria-label={`Chọn trường chuẩn cho ${m.source_column_or_cell}`}
                          style={{ width: 165, padding: "4px 6px", fontSize: 12 }}
                          value={editFields[m.id] ?? (m.proposed_field || "")}
                          onChange={(e) => setEditFields((prev) => ({ ...prev, [m.id]: e.target.value }))}
                        >
                          {STANDARD_FIELDS.map((sf) => (
                            <option key={sf.value} value={sf.value}>
                              {sf.label}
                            </option>
                          ))}
                        </select>
                        {m.proposed_field && (
                          <button type="button" className="btn btn-xs btn-success" onClick={() => void confirmSingleMapping(m, "accepted")}>
                            ✔ Chấp nhận
                          </button>
                        )}
                        <button type="button" className="btn btn-xs btn-primary" onClick={() => void confirmSingleMapping(m, "edited")}>
                          Lưu chọn
                        </button>
                        <button type="button" className="btn btn-xs btn-ghost" onClick={() => void confirmSingleMapping(m, "rejected")}>
                          Bỏ qua
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" className="btn btn-primary" onClick={onGoWorkbench}>
            Tiếp tục sang Bước 2 · Soát lỗi &amp; Sửa Lịch nháp →
          </button>
        </div>
      </section>
    </div>
  );
}

/* ============================================================================
 * BƯỚC 2: BÀN LÀM VIỆC CHIA ĐÔI — LỊCH NHÁP SỬA TẠI DÒNG + KIỂM TRA HC/SC
 * ========================================================================== */
export function WorkbenchWorkspace({
  version,
  versions,
  uploads,
  pendingMappingsCount,
  onSelectVersion,
  onCreateDraftFromVersion,
  onUpdated,
  onInspectSource,
  onGoIngest,
  onGoPublish,
}: {
  version: VersionDetail | null;
  versions: VersionListItem[];
  uploads: UploadRecord[];
  pendingMappingsCount: number;
  onSelectVersion: (versionId: number) => Promise<void>;
  onCreateDraftFromVersion: (versionId: number) => Promise<void>;
  onUpdated: () => Promise<void>;
  onInspectSource: (target: SourceInspectTarget) => void;
  onGoIngest: () => void;
  onGoPublish: () => void;
}) {
  const [quickScope, setQuickScope] = useState<"all" | "blocking" | "pending_room">("all");
  const [classFilter, setClassFilter] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [viewMode, setViewMode] = useState<"table" | "agenda">("table");
  const [inspectorTab, setInspectorTab] = useState<"blocking" | "warning" | "rules">("blocking");
  const [selectedIssueId, setSelectedIssueId] = useState<number | null>(null);

  // State sửa trực tiếp trên dòng (Inline Edit)
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");
  const [editRoom, setEditRoom] = useState("");
  const [editStatus, setEditStatus] = useState<"confirmed" | "tentative" | "pending" | "online">("confirmed");
  const [editInstructor, setEditInstructor] = useState("");
  const [editReason, setEditReason] = useState("Admin sửa trực tiếp trên Lịch nháp");

  const [busyValidate, setBusyValidate] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  if (!version) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Bước 2 · Lịch nháp &amp; Kiểm tra ràng buộc</h2>
        <div className="banner banner-wrn">
          Chưa có phiên bản lịch nào cho dự án này. Hãy quay lại <strong>Bước 1 · Nhập Excel</strong> để tải workbook và tạo Lịch nháp.
        </div>
        <button type="button" className="btn btn-primary" onClick={onGoIngest}>
          ← Quay lại Bước 1 · Nhập Excel
        </button>
      </section>
    );
  }

  const val = version.validation;
  const issues = val?.issues || [];
  const blockingIssues = issues.filter((i) => i.severity === "blocking");
  const warningIssues = issues.filter((i) => i.severity !== "blocking");
  const selectedIssue = issues.find((i) => i.id === selectedIssueId) || null;

  const classOptions = Array.from(new Set(["L3A", "L3B", "L2A", "L2B", ...version.items.map((x) => x.class_name).filter(Boolean)]));

  const itemIssuesMap = new Map<number, ValidationIssueRecord[]>();
  for (const it of version.items) {
    itemIssuesMap.set(
      it.id,
      issues.filter((iss) => doesIssueAffectItem(it, iss)),
    );
  }

  const blockingItemCount = version.items.filter((it) =>
    (itemIssuesMap.get(it.id) || []).some((iss) => iss.severity === "blocking"),
  ).length;
  const pendingRoomCount = version.items.filter((it) => it.room_status === "pending" || it.room_status === "tentative").length;

  const filteredItems = version.items.filter((it) => {
    const itIssues = itemIssuesMap.get(it.id) || [];
    if (selectedIssue && !doesIssueAffectItem(it, selectedIssue)) return false;
    if (quickScope === "blocking" && !itIssues.some((x) => x.severity === "blocking")) return false;
    if (quickScope === "pending_room" && it.room_status !== "pending" && it.room_status !== "tentative") return false;
    if (classFilter && !it.class_name.includes(classFilter)) return false;
    if (dateFilter && it.date !== dateFilter) return false;
    if (keyword.trim()) {
      const q = keyword.trim().toLowerCase();
      if (![it.topic, it.room, it.instructor, it.class_name, `${it.session_type} ${it.session_number}`].join(" ").toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  function beginInlineEdit(it: ScheduleItemRecord) {
    setEditingId(it.id);
    setEditStart(it.start_time);
    setEditEnd(it.end_time);
    setEditRoom(it.room);
    setEditStatus(it.room_status);
    setEditInstructor(it.instructor);
    setEditReason("Admin sửa trực tiếp trên Lịch nháp");
    setMsg("");
    setErr("");
  }

  async function saveInlineEdit(itemId: number) {
    setSavingId(itemId);
    setErr("");
    setMsg("");
    try {
      await api.patch(`/api/versions/${version!.id}/schedule-items/${itemId}`, {
        start_time: editStart,
        end_time: editEnd,
        room: editRoom,
        room_status: editStatus,
        instructor: editInstructor,
        reason: editReason || "Admin sửa trực tiếp trên Lịch nháp",
      });
      setEditingId(null);
      setMsg("✔ Đã lưu sửa đổi & tự động kiểm tra lại ràng buộc HC/SC.");
      await onUpdated();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Không lưu được chỉnh sửa.");
    } finally {
      setSavingId(null);
    }
  }

  async function quickConfirmRoom(it: ScheduleItemRecord) {
    setSavingId(it.id);
    setErr("");
    setMsg("");
    try {
      await api.patch(`/api/versions/${version!.id}/schedule-items/${it.id}`, {
        room_status: "confirmed",
        reason: `Xác nhận nhanh phòng ${it.room}`,
      });
      setMsg(`✔ Đã xác nhận phòng ${it.room} cho ${it.class_name} ${it.session_type} ${it.session_number}.`);
      await onUpdated();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Không thể xác nhận nhanh phòng.");
    } finally {
      setSavingId(null);
    }
  }

  async function reRunValidate() {
    setBusyValidate(true);
    setErr("");
    try {
      await api.post(`/api/versions/${version!.id}/validate`, {});
      setMsg("✔ Đã chạy lại kiểm tra xác định HC/SC.");
      await onUpdated();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Không chạy được kiểm tra.");
    } finally {
      setBusyValidate(false);
    }
  }

  function handleProvenanceClick(p: ScheduleItemRecord["provenance"][number]) {
    if (p.manual_override) return;
    const matchedUp = uploads.find((u) => u.id === p.upload_id || u.original_name === p.file);
    if (!matchedUp) return;
    onInspectSource({
      uploadId: matchedUp.id,
      sheet: p.sheet,
      highlightCell: p.cell_range || p.source_cell,
    });
  }

  function renderProvenanceChips(it: ScheduleItemRecord) {
    return it.provenance.map((p, idx) =>
      p.manual_override ? (
        <span key={idx} className="badge badge-inf" style={{ marginRight: 4, marginBottom: 2 }}>
          ✎ {p.edited_by}: {p.reason}
        </span>
      ) : (
        <button
          key={idx}
          type="button"
          className="provenance-chip"
          title="Bấm để đối chiếu ô gốc trên Excel"
          onClick={() => handleProvenanceClick(p)}
        >
          📄 {p.file} :: {p.sheet} :: {p.cell_range}
        </button>
      ),
    );
  }

  const groupedByDate = (() => {
    const map = new Map<string, ScheduleItemRecord[]>();
    for (const it of filteredItems) {
      const arr = map.get(it.date) || [];
      arr.push(it);
      map.set(it.date, arr);
    }
    return Array.from(map.entries());
  })();

  const isDraft = version.status === "draft";

  return (
    <div>
      {/* THANH ĐIỀU KHIỂN LỊCH NHÁP */}
      <section className="card" style={{ padding: "12px 16px" }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div className="row">
            <h2 style={{ margin: 0, fontSize: 18 }}>Bước 2 · Lịch nháp &amp; Kiểm tra trực tiếp</h2>
            <select
              aria-label="Chọn phiên bản lịch"
              style={{ width: "auto", padding: "5px 10px", fontWeight: 700 }}
              value={version.id}
              onChange={(e) => void onSelectVersion(Number(e.target.value))}
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number} [{v.status}]
                </option>
              ))}
            </select>
            {!isDraft && (
              <button type="button" className="btn btn-sm btn-primary" onClick={() => void onCreateDraftFromVersion(version.id)}>
                ✎ Tạo bản nháp mới từ v{version.version_number} để sửa
              </button>
            )}
          </div>

          <div className="pill-group">
            <button
              type="button"
              className={`pill-btn ${viewMode === "table" ? "active" : ""}`}
              onClick={() => setViewMode("table")}
            >
              📋 Dạng bảng
            </button>
            <button
              type="button"
              className={`pill-btn ${viewMode === "agenda" ? "active" : ""}`}
              onClick={() => setViewMode("agenda")}
            >
              📅 Theo ngày
            </button>
          </div>
        </div>

        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="pill-group">
            <button
              type="button"
              className={`pill-btn ${quickScope === "all" && !selectedIssueId ? "active" : ""}`}
              onClick={() => {
                setQuickScope("all");
                setSelectedIssueId(null);
              }}
            >
              Tất cả ({version.items.length})
            </button>
            <button
              type="button"
              className={`pill-btn ${quickScope === "blocking" ? "danger-active" : ""}`}
              onClick={() => {
                setQuickScope(quickScope === "blocking" ? "all" : "blocking");
                setSelectedIssueId(null);
              }}
            >
              ✖ Đang vướng lỗi ({blockingItemCount})
            </button>
            <button
              type="button"
              className={`pill-btn ${quickScope === "pending_room" ? "active" : ""}`}
              onClick={() => {
                setQuickScope(quickScope === "pending_room" ? "all" : "pending_room");
                setSelectedIssueId(null);
              }}
            >
              ⏳ Phòng chờ ({pendingRoomCount})
            </button>

            <span className="sub" style={{ marginLeft: 4 }}>Lớp:</span>
            <button type="button" className={`pill-btn ${classFilter === "" ? "active" : ""}`} onClick={() => setClassFilter("")}>
              Tất cả
            </button>
            {classOptions.map((c) => (
              <button
                key={c}
                type="button"
                className={`pill-btn ${classFilter === c ? "active" : ""}`}
                onClick={() => setClassFilter(classFilter === c ? "" : c)}
              >
                {c}
              </button>
            ))}
          </div>

          <div className="row">
            <input
              aria-label="Tìm buổi học"
              style={{ width: 200, padding: "5px 9px", fontSize: 12.5 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Tìm phòng, chủ đề, GV…"
            />
            <input
              aria-label="Lọc ngày"
              type="date"
              style={{ width: 145, padding: "4px 8px", fontSize: 12.5 }}
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
            />
          </div>
        </div>
      </section>

      {msg && <div className="banner banner-ok">{msg}</div>}
      {err && <div className="banner banner-err">[LỖI] {err}</div>}
      {selectedIssue && (
        <div className="toast-banner">
          <span>
            Đang lọc buổi liên quan tới lỗi <strong>{selectedIssue.rule_id}</strong>: {selectedIssue.message}
          </span>
          <button type="button" className="btn btn-xs btn-ghost" onClick={() => setSelectedIssueId(null)}>
            Bỏ lọc lỗi
          </button>
        </div>
      )}

      {/* BÀN LÀM VIỆC CHIA ĐÔI */}
      <div className="workbench-split">
        {/* CỘT TRÁI: LỊCH NHÁP TƯƠNG TÁC */}
        <section className="card" style={{ marginBottom: 0 }}>
          {viewMode === "agenda" ? (
            filteredItems.length === 0 ? (
              <div className="banner banner-inf">Không có buổi học nào khớp bộ lọc hiện tại.</div>
            ) : (
              groupedByDate.map(([d, items]) => (
                <div key={d} className="day-group">
                  <div className="day-header">
                    <span>📅 {d}</span>
                    <span className="badge badge-inf">{items.length} buổi</span>
                  </div>
                  {items.map((it) => {
                    const rowIssues = itemIssuesMap.get(it.id) || [];
                    const hasBlock = rowIssues.some((x) => x.severity === "blocking");
                    const canOneClickConfirm =
                      isDraft &&
                      (it.room_status === "pending" || it.room_status === "tentative") &&
                      Boolean(it.room) &&
                      !it.room.toLowerCase().includes("chờ");
                    return (
                      <div key={it.id} className={`session-card ${hasBlock ? "blocking" : ""}`}>
                        <div>
                          <strong>{it.start_time} – {it.end_time}</strong>
                        </div>
                        <div>
                          <span className="badge badge-inf">{it.class_name}</span>
                          <div className="sub">{it.session_type} {it.session_number}</div>
                        </div>
                        <div>
                          <div style={{ fontWeight: 600 }}>{it.topic}</div>
                          <div className="sub">GV: {it.instructor || "Thiếu GV"} {it.assistants.length ? `· ${it.assistants.join(", ")}` : ""}</div>
                          <div style={{ marginTop: 4 }}>{renderProvenanceChips(it)}</div>
                          {hasBlock && (
                            <div className="sub" style={{ color: "var(--danger)", marginTop: 3 }}>
                              ✖ {rowIssues.find((x) => x.severity === "blocking")?.message}
                            </div>
                          )}
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div>
                            <strong>{it.room || "—"}</strong>{" "}
                            <span className={`badge ${it.room_status === "confirmed" || it.room_status === "online" ? "badge-ok" : "badge-err"}`}>
                              [{it.room_status}]
                            </span>
                          </div>
                          {isDraft && (
                            <div className="row" style={{ justifyContent: "flex-end", marginTop: 6 }}>
                              {canOneClickConfirm && (
                                <button
                                  type="button"
                                  className="btn btn-xs btn-success"
                                  disabled={savingId === it.id}
                                  onClick={() => void quickConfirmRoom(it)}
                                >
                                  ✔ Xác nhận phòng
                                </button>
                              )}
                              <button
                                type="button"
                                className="btn btn-xs btn-ghost"
                                onClick={() => {
                                  setViewMode("table");
                                  beginInlineEdit(it);
                                }}
                              >
                                ✎ Sửa
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))
            )
          ) : (
            <div className="table-wrap" style={{ maxHeight: "72vh" }}>
              <table>
                <thead>
                  <tr>
                    <th>Ngày / Giờ</th>
                    <th>Lớp / Buổi</th>
                    <th>Phòng &amp; Trạng thái</th>
                    <th>GV &amp; Chủ đề</th>
                    <th>Provenance (bấm xem ô gốc)</th>
                    <th>Sửa nhanh</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: "center", padding: 20 }}>
                        Không có buổi học nào khớp bộ lọc hiện tại.
                      </td>
                    </tr>
                  ) : (
                    filteredItems.map((it) => {
                      const rowIssues = itemIssuesMap.get(it.id) || [];
                      const hasBlock = rowIssues.some((x) => x.severity === "blocking");
                      const isEditing = editingId === it.id;
                      const canOneClickConfirm =
                        isDraft &&
                        (it.room_status === "pending" || it.room_status === "tentative") &&
                        Boolean(it.room) &&
                        !it.room.toLowerCase().includes("chờ");

                      if (isEditing) {
                        return (
                          <tr
                            key={it.id}
                            className="row-highlight"
                            onKeyDown={(e) => {
                              if (e.key === "Escape") setEditingId(null);
                              if (e.key === "Enter") {
                                e.preventDefault();
                                void saveInlineEdit(it.id);
                              }
                            }}
                          >
                            <td>
                              <strong>{it.date}</strong>
                              <div className="row" style={{ marginTop: 4, flexWrap: "nowrap" }}>
                                <input aria-label="Giờ BĐ" style={{ width: 66, padding: "4px 6px" }} value={editStart} onChange={(e) => setEditStart(e.target.value)} />
                                <input aria-label="Giờ KT" style={{ width: 66, padding: "4px 6px" }} value={editEnd} onChange={(e) => setEditEnd(e.target.value)} />
                              </div>
                            </td>
                            <td>
                              <span className="badge badge-inf">{it.class_name}</span>
                              <div>{it.session_type} {it.session_number}</div>
                            </td>
                            <td>
                              <input
                                aria-label="Phòng"
                                style={{ marginBottom: 4, padding: "4px 6px" }}
                                value={editRoom}
                                onChange={(e) => setEditRoom(e.target.value)}
                                placeholder="vd: H209"
                              />
                              <select
                                aria-label="Trạng thái phòng"
                                style={{ padding: "4px 6px", fontSize: 12 }}
                                value={editStatus}
                                onChange={(e) => setEditStatus(e.target.value as typeof editStatus)}
                              >
                                <option value="confirmed">confirmed</option>
                                <option value="tentative">tentative</option>
                                <option value="pending">pending</option>
                                <option value="online">online</option>
                              </select>
                            </td>
                            <td>
                              <input
                                aria-label="Giảng viên"
                                style={{ marginBottom: 4, padding: "4px 6px" }}
                                value={editInstructor}
                                onChange={(e) => setEditInstructor(e.target.value)}
                                placeholder="Tên giảng viên"
                              />
                              <input
                                aria-label="Lý do chỉnh sửa"
                                style={{ padding: "4px 6px", fontSize: 12 }}
                                value={editReason}
                                onChange={(e) => setEditReason(e.target.value)}
                                placeholder="Lý do chỉnh sửa"
                              />
                            </td>
                            <td className="sub">{renderProvenanceChips(it)}</td>
                            <td>
                              <div className="row">
                                <button
                                  type="button"
                                  className="btn btn-xs btn-primary"
                                  disabled={savingId === it.id}
                                  onClick={() => void saveInlineEdit(it.id)}
                                >
                                  {savingId === it.id ? "Đang lưu…" : "✔ Lưu (Enter)"}
                                </button>
                                <button type="button" className="btn btn-xs btn-ghost" onClick={() => setEditingId(null)}>
                                  Huỷ (Esc)
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      }

                      return (
                        <tr key={it.id} className={`${hasBlock ? "row-blocking" : "row-hover"}`}>
                          <td>
                            <strong>{it.date}</strong>
                            <div className="sub">{it.start_time} – {it.end_time}</div>
                          </td>
                          <td>
                            <span className="badge badge-inf">{it.class_name}</span>
                            <div>{it.session_type} {it.session_number}</div>
                          </td>
                          <td>
                            <strong>{it.room || "—"}</strong>{" "}
                            <span className={`badge ${it.room_status === "confirmed" || it.room_status === "online" ? "badge-ok" : "badge-err"}`}>
                              [{it.room_status}]
                            </span>
                            {canOneClickConfirm && (
                              <div style={{ marginTop: 4 }}>
                                <button
                                  type="button"
                                  className="btn btn-xs btn-success"
                                  disabled={savingId === it.id}
                                  onClick={() => void quickConfirmRoom(it)}
                                >
                                  ✔ Xác nhận phòng
                                </button>
                              </div>
                            )}
                          </td>
                          <td>
                            <div>{it.instructor || <span className="badge badge-err">[Thiếu GV]</span>}</div>
                            <div className="sub">{it.topic}</div>
                            {hasBlock && (
                              <div className="sub" style={{ color: "var(--danger)", marginTop: 3 }}>
                                ✖ {rowIssues.find((x) => x.severity === "blocking")?.rule_id}:{" "}
                                {rowIssues.find((x) => x.severity === "blocking")?.message}
                              </div>
                            )}
                          </td>
                          <td>{renderProvenanceChips(it)}</td>
                          <td>
                            {isDraft && (
                              <button type="button" className="btn btn-xs btn-ghost" onClick={() => beginInlineEdit(it)}>
                                ✎ Sửa nhanh
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* CỘT PHẢI: TRÌNH KIỂM TRA HC/SC TRỰC TIẾP */}
        <aside className="card sticky-inspector" aria-label="Bảng kiểm tra HC và SC trực tiếp">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <h3 style={{ margin: 0 }}>Kiểm tra HC / SC</h3>
              <div className="sub">Ruleset: {val?.ruleset_version} · {val?.finished_at}</div>
            </div>
            <button type="button" className="btn btn-xs btn-ghost" disabled={busyValidate} onClick={reRunValidate}>
              {busyValidate ? "Đang chạy…" : "↻ Kiểm tra lại"}
            </button>
          </div>

          {val?.summary.can_publish ? (
            <div className="banner banner-ok">
              <div><strong>✔ Đã sạch lỗi chặn!</strong> Đủ điều kiện công bố cho Học viên.</div>
              <button type="button" className="btn btn-sm btn-success" style={{ marginTop: 8, width: "100%" }} onClick={onGoPublish}>
                Sang Bước 3 · Duyệt &amp; Công bố →
              </button>
            </div>
          ) : (
            <div className="banner banner-err">
              <strong>✖ Còn {blockingIssues.length} lỗi chặn</strong> (cần xử lý về 0 mới được công bố).
            </div>
          )}

          <div className="pill-group" style={{ marginBottom: 10 }}>
            <button
              type="button"
              className={`pill-btn ${inspectorTab === "blocking" ? "danger-active" : ""}`}
              onClick={() => setInspectorTab("blocking")}
            >
              Lỗi chặn ({blockingIssues.length})
            </button>
            <button
              type="button"
              className={`pill-btn ${inspectorTab === "warning" ? "active" : ""}`}
              onClick={() => setInspectorTab("warning")}
            >
              Cảnh báo ({warningIssues.length})
            </button>
            <button
              type="button"
              className={`pill-btn ${inspectorTab === "rules" ? "active" : ""}`}
              onClick={() => setInspectorTab("rules")}
            >
              12 Quy tắc
            </button>
          </div>

          {inspectorTab === "rules" ? (
            <div className="table-wrap" style={{ maxHeight: 380 }}>
              <table>
                <thead>
                  <tr><th>Mã</th><th>Quy tắc</th><th>KQ</th></tr>
                </thead>
                <tbody>
                  {(val?.summary.rule_statuses || []).map((r) => (
                    <tr key={r.rule_id}>
                      <td><strong>{r.rule_id}</strong></td>
                      <td className="sub">{r.title}</td>
                      <td><SeverityBadge severity={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div>
              {(inspectorTab === "blocking" ? blockingIssues : warningIssues).length === 0 ? (
                <div className="banner banner-ok">
                  {inspectorTab === "blocking" ? "✔ Không còn lỗi chặn nào." : "✔ Không có cảnh báo nào."}
                </div>
              ) : (
                (inspectorTab === "blocking" ? blockingIssues : warningIssues).map((iss) => (
                  <div
                    key={iss.id}
                    className={`issue-card ${selectedIssueId === iss.id ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedIssueId(selectedIssueId === iss.id ? null : iss.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedIssueId(selectedIssueId === iss.id ? null : iss.id);
                      }
                    }}
                  >
                    <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                      <strong>{iss.rule_id}</strong>
                      <SeverityBadge severity={iss.severity} />
                    </div>
                    <div style={{ fontSize: 12.5 }}>{iss.message}</div>
                    <div className="sub" style={{ marginTop: 4 }}>Khắc phục: {iss.remediation}</div>
                    {(iss.rule_id === "HC-MAPPING-PENDING" || pendingMappingsCount > 0) && iss.rule_id === "HC-MAPPING-PENDING" && (
                      <button
                        type="button"
                        className="btn btn-xs btn-primary"
                        style={{ marginTop: 6 }}
                        onClick={(e) => {
                          e.stopPropagation();
                          onGoIngest();
                        }}
                      >
                        Mở bảng xác nhận Mapping (Bước 1) →
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ============================================================================
 * BƯỚC 3: DUYỆT CÔNG BỐ + BẢN NHÁP THÔNG BÁO + XEM TRƯỚC VIEWER
 * ========================================================================== */
export function PublishWorkspace({
  version,
  pendingMappingsCount,
  onPublished,
  onGoIngest,
  onGoWorkbench,
}: {
  version: VersionDetail | null;
  pendingMappingsCount: number;
  onPublished: () => Promise<void>;
  onGoIngest: () => void;
  onGoWorkbench: () => void;
}) {
  const [confirmCheck, setConfirmCheck] = useState(false);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [noticeDraft, setNoticeDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [showViewer, setShowViewer] = useState(true);

  useEffect(() => {
    if (!version) return;
    let active = true;
    api
      .get<{ draft_text: string }>(`/api/versions/${version.id}/announcement-draft`)
      .then((res) => {
        if (active) setNoticeDraft(res.draft_text);
      })
      .catch(() => {
        if (active) setNoticeDraft("");
      });
    return () => {
      active = false;
    };
  }, [version?.id]);

  if (!version) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Bước 3 · Duyệt &amp; Công bố Phiên bản</h2>
        <div className="banner banner-wrn">Chưa có phiên bản lịch nào. Hãy hoàn thành Bước 1 trước.</div>
        <button type="button" className="btn btn-primary" onClick={onGoIngest}>
          ← Sang Bước 1 · Nhập Excel
        </button>
      </section>
    );
  }

  const blockingCount = version.validation?.summary.blocking_count ?? 0;
  const warningCount = version.validation?.summary.warning_count ?? 0;
  const canPub = version.status === "draft" && Boolean(version.validation?.summary.can_publish);

  async function handlePublish() {
    if (!confirmCheck || busy) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const key = `pub-${version!.id}-${Date.now()}`;
      const res = await api.post<{ version: { version_number: number; published_at: string } }>(
        `/api/versions/${version!.id}/publish`,
        { confirm: true, publish_key: key, change_summary: summary || undefined },
      );
      setMsg(`Đã công bố thành công phiên bản v${res.version.version_number} lúc ${res.version.published_at}.`);
      await onPublished();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Công bố thất bại.");
    } finally {
      setBusy(false);
    }
  }

  async function copyAnnouncement() {
    if (!noticeDraft) return;
    try {
      await navigator.clipboard.writeText(noticeDraft);
    } catch {
      const el = document.getElementById("pub-notice-box") as HTMLTextAreaElement | null;
      if (el) {
        el.select();
        document.execCommand("copy");
      }
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  }

  return (
    <div>
      <div className="grid2">
        {/* CỘT TRÁI: KIỂM ĐIỀU KIỆN & CÔNG BỐ */}
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Bước 3 · Phê duyệt Công bố (v{version.version_number})</h2>
          <div className="grid3" style={{ marginBottom: 14 }}>
            <div className="stat-card">
              <div className="sub">Số buổi học</div>
              <div className="stat-num">{version.items.length}</div>
            </div>
            <div className="stat-card">
              <div className="sub">Lỗi chặn (= 0)</div>
              <div className="stat-num" style={{ color: blockingCount === 0 ? "var(--success)" : "var(--danger)" }}>
                {blockingCount}
              </div>
            </div>
            <div className="stat-card">
              <div className="sub">Cảnh báo / Mapping</div>
              <div className="stat-num">{warningCount} / {pendingMappingsCount}</div>
            </div>
          </div>

          {!canPub && version.status === "draft" && (
            <div className="banner banner-err">
              <div>✖ <strong>[CHẶN CÔNG BỐ]</strong> Phiên bản vẫn còn {blockingCount} lỗi chặn bắt buộc.</div>
              <div className="row" style={{ marginTop: 8 }}>
                {pendingMappingsCount > 0 && (
                  <button type="button" className="btn btn-sm btn-primary" onClick={onGoIngest}>
                    Về Bước 1 · Xác nhận Mapping ({pendingMappingsCount})
                  </button>
                )}
                <button type="button" className="btn btn-sm btn-ghost" onClick={onGoWorkbench}>
                  Về Bước 2 · Sửa Lịch nháp
                </button>
              </div>
            </div>
          )}

          {version.status !== "draft" && (
            <div className="banner banner-ok">
              ✔ Phiên bản v{version.version_number} hiện đang ở trạng thái <strong>[{version.status}]</strong>
              {version.published_at ? ` (công bố lúc ${version.published_at})` : ""}.
            </div>
          )}

          <div style={{ marginBottom: 12 }}>
            <label htmlFor="pub-sum">Ghi chú phát hành phiên bản</label>
            <input
              id="pub-sum"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="vd: Đã xác nhận đủ phòng học & giải quyết trùng phòng"
            />
          </div>

          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, width: "auto", marginBottom: 14, cursor: "pointer" }}>
            <input type="checkbox" style={{ width: "auto" }} checked={confirmCheck} onChange={(e) => setConfirmCheck(e.target.checked)} />
            Tôi (Admin) đã kiểm tra cảnh báo còn lại và xác nhận công bố bản lịch này cho Học viên / Viewer.
          </label>

          <div className="row">
            <button type="button" className="btn btn-success" disabled={!canPub || !confirmCheck || busy} onClick={handlePublish}>
              {busy ? "Đang công bố…" : "🚀 Xác nhận Công bố Phiên bản"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={onGoWorkbench}>
              ← Quay lại Bước 2
            </button>
          </div>
          {msg && <div className="banner banner-ok" style={{ marginTop: 12 }}>[THÀNH CÔNG] {msg}</div>}
          {err && <div className="banner banner-err" style={{ marginTop: 12 }}>[LỖI] {err}</div>}
        </section>

        {/* CỘT PHẢI: BẢN NHÁP THÔNG BÁO SẴN SÀNG COPY */}
        <section className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <div>
              <h3 style={{ margin: 0 }}>Bản nháp thông báo kèm căn cứ</h3>
              <div className="sub">Hệ thống KHÔNG tự gửi tin nhắn ra ngoài — Admin kiểm tra rồi copy thủ công.</div>
            </div>
            <button type="button" className="btn btn-sm btn-primary" disabled={!noticeDraft} onClick={() => void copyAnnouncement()}>
              {copied ? "✔ Đã sao chép!" : "📋 Sao chép"}
            </button>
          </div>
          <textarea
            id="pub-notice-box"
            rows={13}
            readOnly
            value={noticeDraft || "Đang tải bản nháp thông báo…"}
          />
        </section>
      </div>

      {/* XEM TRƯỚC TRANG VIEWER NGAY BÊN DƯỚI */}
      <div style={{ marginTop: 4 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <strong>👁 Xem trước trang Viewer (dữ liệu Học viên nhìn thấy sau khi công bố)</strong>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setShowViewer(!showViewer)}>
            {showViewer ? "Thu gọn xem trước" : "Mở xem trước Viewer"}
          </button>
        </div>
        {showViewer && <ViewerView key={`pub-vw-${version.status}-${version.published_at || ""}`} />}
      </div>
    </div>
  );
}

/* ============================================================================
 * BƯỚC 4: LỊCH SỬ PHIÊN BẢN, ROLLBACK & NHẬT KÝ AI / AUDIT
 * ========================================================================== */
export function HistoryAuditView({
  project,
  versions,
  aiRuns,
  auditLogs,
  onSelectVersion,
  onRollbackDraft,
}: {
  project: ProjectSummary | null;
  versions: VersionListItem[];
  aiRuns: AiRunRecord[];
  auditLogs: AuditLogRecord[];
  onSelectVersion: (versionId: number) => Promise<void>;
  onRollbackDraft: (fromVersionId: number) => Promise<void>;
}) {
  const [subTab, setSubTab] = useState<"versions" | "ai" | "audit">("versions");
  const [auditQuery, setAuditQuery] = useState("");

  const filteredAudit = auditLogs.filter((l) => {
    if (!auditQuery.trim()) return true;
    const q = auditQuery.trim().toLowerCase();
    return [l.actor_username, l.action, l.entity_type, l.entity_id].join(" ").toLowerCase().includes(q);
  });

  return (
    <section className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>Bước 4 · Phiên bản, Rollback &amp; Nhật ký — {project?.name || "—"}</h2>
      </div>

      <div className="subtabs">
        <button
          type="button"
          className={`pill-btn ${subTab === "versions" ? "active" : ""}`}
          onClick={() => setSubTab("versions")}
        >
          Phiên bản &amp; Rollback ({versions.length})
        </button>
        <button
          type="button"
          className={`pill-btn ${subTab === "ai" ? "active" : ""}`}
          onClick={() => setSubTab("ai")}
        >
          Chi phí &amp; Cache AI ({aiRuns.length})
        </button>
        <button
          type="button"
          className={`pill-btn ${subTab === "audit" ? "active" : ""}`}
          onClick={() => setSubTab("audit")}
        >
          Nhật ký bảo mật Audit ({auditLogs.length})
        </button>
      </div>

      {subTab === "versions" && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Phiên bản</th><th>Trạng thái</th><th>Tạo lúc</th><th>Công bố lúc</th><th>Ghi chú</th><th>Thao tác</th></tr>
            </thead>
            <tbody>
              {versions.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: "center" }}>Chưa có phiên bản nào.</td></tr>
              ) : (
                versions.map((v) => (
                  <tr key={v.id} className="row-hover">
                    <td><strong>v{v.version_number}</strong></td>
                    <td><span className={`badge ${v.status === "published" ? "badge-ok" : "badge-inf"}`}>[{v.status}]</span></td>
                    <td className="sub">{v.created_at}</td>
                    <td className="sub">{v.published_at || "—"}</td>
                    <td>{v.change_summary}</td>
                    <td>
                      <div className="row">
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => void onSelectVersion(v.id)}>
                          Mở tại Bước 2
                        </button>
                        <button type="button" className="btn btn-sm btn-primary" onClick={() => void onRollbackDraft(v.id)}>
                          ↻ Tạo Draft mới (Rollback)
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {subTab === "ai" && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Provider / Model</th><th>Trạng thái</th><th>Token (In/Out)</th><th>Chi phí</th><th>Thời gian</th></tr></thead>
            <tbody>
              {aiRuns.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: "center" }}>Chưa có lượt gọi AI nào.</td></tr>
              ) : (
                aiRuns.map((r) => (
                  <tr key={r.id}>
                    <td>{r.provider} / {r.model}<div className="sub">{r.prompt_version} · {r.input_hash.slice(0, 10)}…</div></td>
                    <td><span className="badge badge-inf">[{r.status}]</span></td>
                    <td>{r.token_in} / {r.token_out}</td>
                    <td>${r.estimated_cost.toFixed(6)}</td>
                    <td className="sub">{r.created_at}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {subTab === "audit" && (
        <div>
          <div style={{ marginBottom: 10, maxWidth: 340 }}>
            <input
              aria-label="Lọc nhật ký audit"
              value={auditQuery}
              onChange={(e) => setAuditQuery(e.target.value)}
              placeholder="Lọc theo hành động (PUBLISH, UPLOAD…) hoặc tài khoản"
            />
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Thời gian</th><th>Tài khoản</th><th>Hành động</th><th>Đối tượng</th></tr></thead>
              <tbody>
                {filteredAudit.map((l) => (
                  <tr key={l.id}>
                    <td className="sub">{l.timestamp}</td>
                    <td><strong>{l.actor_username}</strong></td>
                    <td><span className="badge badge-inf">{l.action}</span></td>
                    <td className="sub">{l.entity_type} #{l.entity_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

/* Giữ export helper tên gợi nhớ nếu cần dùng ở ngoài */
export type { AdminWorkspaceId };
