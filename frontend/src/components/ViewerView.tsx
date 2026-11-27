import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

interface PublicItem {
  id: number;
  date: string;
  class_name: string;
  session_type: string;
  session_number: number;
  start_time: string;
  end_time: string;
  topic: string;
  room: string;
  instructor: string;
  room_status: string;
}

interface PublicScheduleResponse {
  projects: { id: number; name: string; course_code: string }[];
  active_version: {
    project_id: number;
    project_name: string;
    version_number: number;
    published_at: string | null;
  } | null;
  items: PublicItem[];
}

const DEFAULT_CLASSES = ["L3A", "L3B", "L2A", "L2B"];

export function ViewerView() {
  const [data, setData] = useState<PublicScheduleResponse | null>(null);
  const [projectId, setProjectId] = useState<string>("");
  const [className, setClassName] = useState<string>("");
  const [dateFilter, setDateFilter] = useState<string>("");
  const [sessionType, setSessionType] = useState<string>("");
  const [keyword, setKeyword] = useState<string>("");
  const [viewMode, setViewMode] = useState<"agenda" | "table">("agenda");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  async function loadSchedule() {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (projectId) params.set("project_id", projectId);
      if (className) params.set("class_name", className);
      if (dateFilter) params.set("date", dateFilter);
      if (sessionType) params.set("session_type", sessionType);
      const res = await api.get<PublicScheduleResponse>(`/api/public/schedule?${params.toString()}`);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được lịch công bố.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSchedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, className, dateFilter, sessionType]);

  const classOptions = useMemo(() => {
    const set = new Set(DEFAULT_CLASSES);
    (data?.items || []).forEach((it) => {
      if (it.class_name) set.add(it.class_name);
    });
    return Array.from(set);
  }, [data]);

  const filteredItems = useMemo(() => {
    const q = keyword.trim().toLowerCase();
    const list = data?.items || [];
    if (!q) return list;
    return list.filter((it) =>
      [it.topic, it.room, it.instructor, it.class_name, `${it.session_type} ${it.session_number}`]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [data, keyword]);

  const groupedByDate = useMemo(() => {
    const map = new Map<string, PublicItem[]>();
    for (const it of filteredItems) {
      const arr = map.get(it.date) || [];
      arr.push(it);
      map.set(it.date, arr);
    }
    return Array.from(map.entries());
  }, [filteredItems]);

  function resetFilters() {
    setClassName("");
    setSessionType("");
    setDateFilter("");
    setKeyword("");
  }

  return (
    <section className="card" aria-label="Lịch công bố cho người xem">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h2 style={{ margin: "0 0 4px" }}>Lịch đào tạo đã công bố</h2>
          <div className="sub">
            Chế độ chỉ đọc — chỉ hiển thị phiên bản lịch chính thức đã được Admin phê duyệt (ẩn dữ liệu nháp &amp; thông tin nội bộ).
          </div>
        </div>
        <div className="row">
          {data?.active_version && (
            <span className="badge badge-ok">
              [ĐÃ CÔNG BỐ] {data.active_version.project_name} · v{data.active_version.version_number}
            </span>
          )}
          <div className="pill-group" role="group" aria-label="Kiểu hiển thị lịch">
            <button
              type="button"
              className={`pill-btn ${viewMode === "agenda" ? "active" : ""}`}
              onClick={() => setViewMode("agenda")}
            >
              📅 Theo ngày
            </button>
            <button
              type="button"
              className={`pill-btn ${viewMode === "table" ? "active" : ""}`}
              onClick={() => setViewMode("table")}
            >
              📋 Dạng bảng
            </button>
          </div>
        </div>
      </div>

      {/* Bộ lọc 1 chạm */}
      <div className="card" style={{ background: "var(--surface-2)", padding: "12px 14px", marginBottom: 14 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <div className="pill-group" role="group" aria-label="Chọn lớp nhanh">
            <span className="sub" style={{ marginRight: 4, fontWeight: 700 }}>Lớp:</span>
            <button type="button" className={`pill-btn ${className === "" ? "active" : ""}`} onClick={() => setClassName("")}>
              Tất cả
            </button>
            {classOptions.map((c) => (
              <button
                key={c}
                type="button"
                className={`pill-btn ${className === c ? "active" : ""}`}
                onClick={() => setClassName(className === c ? "" : c)}
              >
                {c}
              </button>
            ))}
          </div>

          <div className="pill-group" role="group" aria-label="Loại buổi">
            <span className="sub" style={{ marginRight: 4, fontWeight: 700 }}>Loại:</span>
            {[
              { id: "", label: "LEC + LAB" },
              { id: "LEC", label: "LEC" },
              { id: "LAB", label: "LAB" },
            ].map((t) => (
              <button
                key={t.id || "ALL"}
                type="button"
                className={`pill-btn ${sessionType === t.id ? "active" : ""}`}
                onClick={() => setSessionType(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid3">
          <div>
            <label htmlFor="vw-proj">Khoá học / Dự án</label>
            <select id="vw-proj" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Mặc định (mới nhất)</option>
              {(data?.projects || []).map((p) => (
                <option key={p.id} value={String(p.id)}>
                  {p.name} ({p.course_code})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="vw-kw">Tìm nhanh (chủ đề, phòng, giảng viên)</label>
            <input
              id="vw-kw"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Gõ phòng C201, ReAct, tên GV…"
            />
          </div>
          <div>
            <label htmlFor="vw-date">Lọc theo ngày</label>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input id="vw-date" type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
              {(className || sessionType || dateFilter || keyword) && (
                <button type="button" className="btn btn-sm btn-ghost" onClick={resetFilters}>
                  Xoá lọc
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {error && <div className="banner banner-err">[LỖI] {error}</div>}
      {loading && <div className="banner banner-inf">Đang tải lịch đã công bố…</div>}

      {!loading && !data?.active_version && (
        <div className="banner banner-wrn">
          [TRỐNG] Chưa có phiên bản lịch nào được Admin công bố.
        </div>
      )}

      {!loading && data?.active_version && (
        <>
          <div className="sub" style={{ marginBottom: 10 }}>
            Công bố lúc: <strong>{data.active_version.published_at || "—"}</strong> · Hiển thị{" "}
            <strong>{filteredItems.length}</strong> buổi học
          </div>

          {filteredItems.length === 0 ? (
            <div className="banner banner-inf">Không có buổi học nào khớp bộ lọc hiện tại.</div>
          ) : viewMode === "agenda" ? (
            <div>
              {groupedByDate.map(([d, items]) => (
                <div key={d} className="day-group">
                  <div className="day-header">
                    <span>📅 {d}</span>
                    <span className="badge badge-inf">{items.length} buổi</span>
                  </div>
                  {items.map((it) => (
                    <div key={it.id} className="session-card">
                      <div>
                        <strong>{it.start_time} – {it.end_time}</strong>
                      </div>
                      <div>
                        <span className="badge badge-inf">{it.class_name}</span>
                        <div className="sub" style={{ marginTop: 2 }}>{it.session_type} {it.session_number}</div>
                      </div>
                      <div>
                        <div style={{ fontWeight: 600 }}>{it.topic || "—"}</div>
                        <div className="sub">Giảng viên: {it.instructor || "—"}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <strong>{it.room || "—"}</strong>{" "}
                        <span className="badge badge-ok">[{it.room_status}]</span>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ngày</th>
                    <th>Giờ học</th>
                    <th>Lớp</th>
                    <th>Buổi</th>
                    <th>Chủ đề</th>
                    <th>Phòng / Trạng thái</th>
                    <th>Giảng viên</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((it) => (
                    <tr key={it.id} className="row-hover">
                      <td><strong>{it.date}</strong></td>
                      <td>{it.start_time} – {it.end_time}</td>
                      <td><span className="badge badge-inf">{it.class_name}</span></td>
                      <td>{it.session_type} {it.session_number}</td>
                      <td>{it.topic}</td>
                      <td>
                        <strong>{it.room || "—"}</strong>{" "}
                        <span className="badge badge-ok">[{it.room_status}]</span>
                      </td>
                      <td>{it.instructor || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
