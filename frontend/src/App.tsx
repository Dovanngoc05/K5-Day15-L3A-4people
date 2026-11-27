import { useEffect, useState } from "react";
import { api, setCsrfToken } from "./api";
import {
  HistoryAuditView,
  IngestWorkspace,
  PublishWorkspace,
  SourceInspectorDrawer,
  WorkbenchWorkspace,
  type VersionListItem,
} from "./components/AdminViews";
import { ViewerView } from "./components/ViewerView";
import type {
  AdminWorkspaceId,
  AiRunRecord,
  AuditLogRecord,
  HealthInfo,
  MappingRecord,
  ProjectSummary,
  SourceInspectTarget,
  UploadRecord,
  UserInfo,
  VersionDetail,
} from "./types";

const WORKSPACE_STEPS: { id: Exclude<AdminWorkspaceId, "viewer_preview">; step: string; title: string }[] = [
  { id: "ingest", step: "1", title: "Nhập Excel & Mapping" },
  { id: "workbench", step: "2", title: "Lịch nháp & Kiểm tra" },
  { id: "publish", step: "3", title: "Duyệt & Công bố" },
  { id: "history", step: "4", title: "Phiên bản & Nhật ký" },
];

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light",
  );
  const [user, setUser] = useState<UserInfo | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginErr, setLoginErr] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);

  const [workspace, setWorkspace] = useState<AdminWorkspaceId>("ingest");
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number>(0);
  const [uploads, setUploads] = useState<UploadRecord[]>([]);
  const [projectMappings, setProjectMappings] = useState<MappingRecord[]>([]);
  const [pendingMappingsCount, setPendingMappingsCount] = useState<number>(0);
  const [versions, setVersions] = useState<VersionListItem[]>([]);
  const [activeVersion, setActiveVersion] = useState<VersionDetail | null>(null);
  const [aiRuns, setAiRuns] = useState<AiRunRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);

  // Modal tạo dự án mới & Ngăn trượt đối chiếu ô nguồn
  const [showNewProjModal, setShowNewProjModal] = useState(false);
  const [newProjName, setNewProjName] = useState("");
  const [newProjCode, setNewProjCode] = useState("AI20K-K9");
  const [newProjScope, setNewProjScope] = useState("L3A,L3B,L2A,L2B");
  const [projErr, setProjErr] = useState("");
  const [inspectTarget, setInspectTarget] = useState<SourceInspectTarget | null>(null);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("a5-theme", next);
  }

  async function refreshAdminData(projIdOverride?: number, versionIdOverride?: number) {
    const pRes = await api.get<{ projects: ProjectSummary[] }>("/api/projects");
    setProjects(pRes.projects);
    const chosenId = projIdOverride || selectedProjectId || pRes.projects[0]?.id || 0;
    setSelectedProjectId(chosenId);
    if (!chosenId) {
      setUploads([]);
      setProjectMappings([]);
      setPendingMappingsCount(0);
      setVersions([]);
      setActiveVersion(null);
      setAiRuns([]);
      return;
    }

    const [uRes, mRes, vRes, aiRes, auRes] = await Promise.all([
      api.get<{ uploads: UploadRecord[] }>(`/api/projects/${chosenId}/uploads`),
      api.get<{ mappings: MappingRecord[]; pending_count: number }>(`/api/projects/${chosenId}/mappings`),
      api.get<{ versions: VersionListItem[] }>(`/api/projects/${chosenId}/versions`),
      api.get<{ runs: AiRunRecord[] }>(`/api/projects/${chosenId}/ai-runs`),
      api.get<{ logs: AuditLogRecord[] }>("/api/audit"),
    ]);

    setUploads(uRes.uploads);
    setProjectMappings(mRes.mappings);
    setPendingMappingsCount(mRes.pending_count);
    setVersions(vRes.versions);
    setAiRuns(aiRes.runs);
    setAuditLogs(auRes.logs);

    const targetVerId =
      versionIdOverride ||
      vRes.versions.find((v) => v.status === "draft")?.id ||
      vRes.versions[0]?.id ||
      0;
    if (targetVerId) {
      const detail = await api.get<VersionDetail>(`/api/versions/${targetVerId}`);
      setActiveVersion(detail);
    } else {
      setActiveVersion(null);
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const h = await api.get<HealthInfo>("/api/health");
        setHealth(h);
      } catch {
        // Bỏ qua nếu backend chưa phản hồi health
      }
      try {
        const me = await api.get<{ user: UserInfo; csrf_token: string }>("/api/auth/me");
        setCsrfToken(me.csrf_token);
        setUser(me.user);
        if (me.user.role === "admin") {
          await refreshAdminData();
        }
      } catch {
        setUser(null);
      } finally {
        setCheckingAuth(false);
      }
    }
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Phím tắt nhanh cho Admin: Alt+1..4 chuyển bước, Esc đóng modal/drawer
  useEffect(() => {
    if (!user || user.role !== "admin") return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setInspectTarget(null);
        setShowNewProjModal(false);
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.altKey) {
        if (e.key === "1") { e.preventDefault(); setWorkspace("ingest"); }
        if (e.key === "2") { e.preventDefault(); setWorkspace("workbench"); }
        if (e.key === "3") { e.preventDefault(); setWorkspace("publish"); }
        if (e.key === "4") { e.preventDefault(); setWorkspace("history"); }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [user]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginBusy(true);
    setLoginErr("");
    try {
      const res = await api.post<{ user: UserInfo; csrf_token: string }>("/api/auth/login", {
        username,
        password,
      });
      setCsrfToken(res.csrf_token);
      setUser(res.user);
      setPassword("");
      if (res.user.role === "admin") {
        await refreshAdminData();
        setWorkspace("ingest");
      }
    } catch (ex) {
      setLoginErr(ex instanceof Error ? ex.message : "Đăng nhập thất bại.");
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout", {});
    } catch {
      // ignore
    }
    setCsrfToken("");
    setUser(null);
    setProjects([]);
    setActiveVersion(null);
    setInspectTarget(null);
  }

  async function handleCreateProject(e: React.FormEvent) {
    e.preventDefault();
    setProjErr("");
    try {
      const created = await api.post<{ id: number }>("/api/projects", {
        name: newProjName,
        course_code: newProjCode,
        classes_scope: newProjScope,
        ai_enabled: true,
        ai_budget_usd: 1.0,
      });
      setNewProjName("");
      setShowNewProjModal(false);
      await refreshAdminData(created.id);
      setWorkspace("ingest");
    } catch (ex) {
      setProjErr(ex instanceof Error ? ex.message : "Lỗi tạo dự án.");
    }
  }

  async function handleCreateDraft(uploadIds: number[]) {
    if (!selectedProjectId) return;
    const res = await api.post<{ id: number }>(`/api/projects/${selectedProjectId}/versions`, {
      upload_ids: uploadIds,
      change_summary: `Tổng hợp từ ${uploadIds.length} workbook`,
    });
    await refreshAdminData(selectedProjectId, res.id);
    setWorkspace("workbench");
  }

  async function handleRollback(fromVersionId: number) {
    if (!selectedProjectId) return;
    const res = await api.post<{ id: number }>(`/api/projects/${selectedProjectId}/versions`, {
      from_version_id: fromVersionId,
    });
    await refreshAdminData(selectedProjectId, res.id);
    setWorkspace("workbench");
  }

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;
  const valSummary = activeVersion?.validation?.summary;
  const blockingCount = valSummary?.blocking_count ?? 0;

  return (
    <div>
      {/* TOPBAR NGỮ CẢNH */}
      <header className="topbar">
        <div className="brand">
          <div className="logo">A5</div>
          <div>
            <div>Trợ lý Tổng hợp &amp; Kiểm tra Lịch AI20K</div>
            <div className="sub">Quy trình 4 bước nhanh · Kiểm tra xác định HC/SC · Provenance</div>
          </div>
        </div>

        {user?.role === "admin" && (
          <div className="topbar-ctx">
            <select
              aria-label="Chọn dự án làm việc"
              style={{ width: "auto", minWidth: 210, padding: "5px 10px", fontWeight: 600 }}
              value={selectedProjectId}
              onChange={(e) => {
                const nextId = Number(e.target.value);
                void refreshAdminData(nextId);
              }}
            >
              {projects.length === 0 ? (
                <option value={0}>Chưa có dự án nào</option>
              ) : (
                projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.course_code})
                  </option>
                ))
              )}
            </select>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setShowNewProjModal(true)}>
              + Dự án mới
            </button>

            {activeVersion && (
              <button
                type="button"
                className={`badge ${valSummary?.can_publish ? "badge-ok" : "badge-err"}`}
                style={{ cursor: "pointer", padding: "5px 10px" }}
                onClick={() => setWorkspace(valSummary?.can_publish ? "publish" : "workbench")}
                title="Bấm để chuyển nhanh tới bước xử lý"
              >
                v{activeVersion.version_number} [{activeVersion.status}] ·{" "}
                {valSummary?.can_publish ? "✔ Sẵn sàng công bố" : `✖ ${blockingCount} lỗi chặn`}
              </button>
            )}
          </div>
        )}

        <div className="row">
          {user?.role === "admin" && (
            <button
              type="button"
              className={`btn btn-sm ${workspace === "viewer_preview" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setWorkspace(workspace === "viewer_preview" ? "workbench" : "viewer_preview")}
            >
              {workspace === "viewer_preview" ? "← Quay lại Quản trị" : "👁 Xem như Học viên"}
            </button>
          )}
          {user && (
            <span className="badge badge-inf">
              {user.username} ({user.role.toUpperCase()})
            </span>
          )}
          <button type="button" className="btn btn-sm btn-ghost" onClick={toggleTheme} aria-label="Đổi giao diện Sáng / Tối">
            {theme === "dark" ? "☀ Sáng" : "🌙 Tối"}
          </button>
          {user && (
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => void handleLogout()}>
              Đăng xuất
            </button>
          )}
        </div>
      </header>

      {/* BODY */}
      {checkingAuth ? (
        <main className="container">
          <div className="banner banner-inf">Đang kiểm tra phiên đăng nhập…</div>
        </main>
      ) : !user ? (
        <main className="container" style={{ maxWidth: 460, marginTop: 48 }}>
          <section className="card">
            <h1 style={{ marginTop: 0, fontSize: 20 }}>Đăng nhập hệ thống</h1>
            <p className="sub">
              Sử dụng tài khoản <b>Admin</b> (Ban đào tạo / Key Coach) hoặc <b>Viewer</b> được tạo qua CLI.
            </p>
            {health?.is_fake_ai && (
              <div className="banner banner-wrn">
                [AI_PROVIDER=fake] Hệ thống đang dùng AI giả lập offline.
              </div>
            )}
            <form onSubmit={handleLogin}>
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="lg-user">Tên đăng nhập</label>
                <input id="lg-user" required autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label htmlFor="lg-pass">Mật khẩu</label>
                <input id="lg-pass" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={loginBusy}>
                {loginBusy ? "Đang xác thực…" : "Đăng nhập"}
              </button>
            </form>
            {loginErr && <div className="banner banner-err" style={{ marginTop: 12 }}>✖ [TỪ CHỐI] {loginErr}</div>}
          </section>
        </main>
      ) : user.role === "viewer" ? (
        <main className="container">
          <ViewerView />
        </main>
      ) : (
        <div className="app-shell">
          {/* THANH ĐIỀU HƯỚNG 4 BƯỚC BÊN TRÁI */}
          <aside className="sidebar" aria-label="Tiến trình làm việc 4 bước">
            <nav className="step-nav">
              {WORKSPACE_STEPS.map((st) => {
                let badgeNode: JSX.Element | null = null;
                if (st.id === "ingest") {
                  if (pendingMappingsCount > 0) {
                    badgeNode = <span className="badge badge-wrn">{pendingMappingsCount} chờ</span>;
                  } else if (uploads.filter((u) => u.status === "parsed").length > 0) {
                    badgeNode = <span className="badge badge-ok">{uploads.filter((u) => u.status === "parsed").length} file</span>;
                  }
                } else if (st.id === "workbench" && activeVersion) {
                  badgeNode = blockingCount > 0 ? (
                    <span className="badge badge-err">✖ {blockingCount}</span>
                  ) : (
                    <span className="badge badge-ok">✔ Đạt</span>
                  );
                } else if (st.id === "publish" && activeVersion) {
                  if (activeVersion.status === "published") {
                    badgeNode = <span className="badge badge-ok">Đã đăng</span>;
                  } else if (valSummary?.can_publish) {
                    badgeNode = <span className="badge badge-ok">Sẵn sàng</span>;
                  }
                } else if (st.id === "history" && versions.length > 0) {
                  badgeNode = <span className="badge badge-inf">{versions.length} bản</span>;
                }

                return (
                  <button
                    key={st.id}
                    type="button"
                    className={`step-btn ${workspace === st.id ? "active" : ""}`}
                    onClick={() => setWorkspace(st.id)}
                  >
                    <span className="step-title">
                      <span className="step-num">{st.step}</span>
                      <span>{st.title}</span>
                    </span>
                    {badgeNode}
                  </button>
                );
              })}
            </nav>

            <section className="card" style={{ padding: "12px 14px", marginBottom: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 6 }}>Tóm tắt nhanh</div>
              <div className="sub">
                <div>• Phiên bản công bố: <b>{selectedProject?.active_published_version_id ? `#${selectedProject.active_published_version_id}` : "Chưa có"}</b></div>
                <div>• Tổng buổi hiện tại: <b>{activeVersion?.items.length ?? 0}</b></div>
                <div>• AI Provider: <b>{health?.ai_provider || "fake"}</b></div>
                <div style={{ marginTop: 6 }}>Phím tắt: <code>Alt+1..4</code> chuyển bước · <code>Esc</code> đóng ngăn xem nguồn.</div>
              </div>
            </section>
          </aside>

          {/* VÙNG LÀM VIỆC CHÍNH */}
          <main className="main-stage">
            {projects.length === 0 ? (
              <section className="card" style={{ maxWidth: 560, margin: "24px auto" }}>
                <h2 style={{ marginTop: 0 }}>Khởi tạo khoá học đầu tiên</h2>
                <p className="sub">
                  Tạo khoá học mới hoặc chạy <code>python -m backend.cli seed-synthetic</code> để nạp dữ liệu mẫu.
                </p>
                <form onSubmit={handleCreateProject}>
                  <div style={{ marginBottom: 10 }}>
                    <label htmlFor="empty-p-name">Tên dự án / khoá học</label>
                    <input id="empty-p-name" required value={newProjName} onChange={(e) => setNewProjName(e.target.value)} placeholder="vd: Khoá 9 — Lịch tháng 4/2027" />
                  </div>
                  <div className="grid2" style={{ marginBottom: 12 }}>
                    <div>
                      <label htmlFor="empty-p-code">Mã khoá</label>
                      <input id="empty-p-code" value={newProjCode} onChange={(e) => setNewProjCode(e.target.value)} />
                    </div>
                    <div>
                      <label htmlFor="empty-p-scope">Phạm vi lớp</label>
                      <input id="empty-p-scope" value={newProjScope} onChange={(e) => setNewProjScope(e.target.value)} />
                    </div>
                  </div>
                  <button type="submit" className="btn btn-primary">Tạo dự án &amp; Bắt đầu Bước 1 →</button>
                </form>
                {projErr && <div className="banner banner-err" style={{ marginTop: 10 }}>[LỖI] {projErr}</div>}
              </section>
            ) : (
              <>
                {workspace === "ingest" && (
                  <IngestWorkspace
                    project={selectedProject}
                    health={health}
                    uploads={uploads}
                    mappings={projectMappings}
                    onUploaded={async (draftId, autoGo) => {
                      await refreshAdminData(selectedProjectId, draftId);
                      if (autoGo) setWorkspace("workbench");
                    }}
                    onMappingsChanged={() => refreshAdminData(selectedProjectId, activeVersion?.id)}
                    onCreateDraftFromUploads={handleCreateDraft}
                    onInspectSource={(t) => setInspectTarget(t)}
                    onGoWorkbench={() => setWorkspace("workbench")}
                  />
                )}
                {workspace === "workbench" && (
                  <WorkbenchWorkspace
                    version={activeVersion}
                    versions={versions}
                    uploads={uploads}
                    pendingMappingsCount={pendingMappingsCount}
                    onSelectVersion={(vid) => refreshAdminData(selectedProjectId, vid)}
                    onCreateDraftFromVersion={handleRollback}
                    onUpdated={() => refreshAdminData(selectedProjectId, activeVersion?.id)}
                    onInspectSource={(t) => setInspectTarget(t)}
                    onGoIngest={() => setWorkspace("ingest")}
                    onGoPublish={() => setWorkspace("publish")}
                  />
                )}
                {workspace === "publish" && (
                  <PublishWorkspace
                    version={activeVersion}
                    pendingMappingsCount={pendingMappingsCount}
                    onPublished={() => refreshAdminData(selectedProjectId, activeVersion?.id)}
                    onGoIngest={() => setWorkspace("ingest")}
                    onGoWorkbench={() => setWorkspace("workbench")}
                  />
                )}
                {workspace === "history" && (
                  <HistoryAuditView
                    project={selectedProject}
                    versions={versions}
                    aiRuns={aiRuns}
                    auditLogs={auditLogs}
                    onSelectVersion={async (vid) => {
                      await refreshAdminData(selectedProjectId, vid);
                      setWorkspace("workbench");
                    }}
                    onRollbackDraft={handleRollback}
                  />
                )}
                {workspace === "viewer_preview" && <ViewerView />}
              </>
            )}
          </main>
        </div>
      )}

      {/* NGĂN TRƯỢT XEM Ô NGUỒN EXCEL */}
      <SourceInspectorDrawer
        target={inspectTarget}
        uploads={uploads}
        onClose={() => setInspectTarget(null)}
      />

      {/* HỘP THOẠI TẠO DỰ ÁN MỚI */}
      {showNewProjModal && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Tạo dự án mới"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowNewProjModal(false);
          }}
        >
          <section className="modal-card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>+ Tạo dự án / khoá học mới</h3>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setShowNewProjModal(false)}>✕</button>
            </div>
            <form onSubmit={handleCreateProject}>
              <div style={{ marginBottom: 10 }}>
                <label htmlFor="m-p-name">Tên dự án / khoá học</label>
                <input id="m-p-name" required value={newProjName} onChange={(e) => setNewProjName(e.target.value)} placeholder="vd: Khoá 9 — Lịch tháng 4/2027" />
              </div>
              <div className="grid2" style={{ marginBottom: 14 }}>
                <div>
                  <label htmlFor="m-p-code">Mã khoá</label>
                  <input id="m-p-code" value={newProjCode} onChange={(e) => setNewProjCode(e.target.value)} />
                </div>
                <div>
                  <label htmlFor="m-p-scope">Phạm vi lớp</label>
                  <input id="m-p-scope" value={newProjScope} onChange={(e) => setNewProjScope(e.target.value)} />
                </div>
              </div>
              {projErr && <div className="banner banner-err">[LỖI] {projErr}</div>}
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <button type="button" className="btn btn-ghost" onClick={() => setShowNewProjModal(false)}>Huỷ</button>
                <button type="submit" className="btn btn-primary">Tạo &amp; chuyển tới Bước 1</button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
