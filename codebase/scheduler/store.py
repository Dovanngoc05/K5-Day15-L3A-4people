"""All durable application records live in XLSX; atomic replace + file lock."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import secrets

from filelock import FileLock

from .excel import SCHEMA, atomic_write, empty_data, read_tables, text


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.root / "store.lock"), timeout=15)
        with self.lock:
            if not (self.root / "state.xlsx").exists():
                atomic_write(self.root / "state.xlsx", {"Meta": [{"key": "published", "value": ""}], "Audit": [], "Accounts": []})
            if not (self.root / "dataset.xlsx").exists():
                atomic_write(self.root / "dataset.xlsx", empty_data(), SCHEMA)

    def state(self):
        return read_tables(self.root / "state.xlsx")

    def data(self):
        return read_tables(self.root / "dataset.xlsx")

    def fingerprint(self):
        return hashlib.sha256((self.root / "dataset.xlsx").read_bytes()).hexdigest()

    def audit(self, state, actor, action, detail=""):
        state.setdefault("Audit", []).append(dict(time=stamp(), actor=actor, action=action, detail=text(detail)[:1500]))

    def save_data(self, tables, actor, detail):
        # Caller holds self.lock throughout the read-modify-write operation.
        atomic_write(self.root / "dataset.xlsx", {k: tables.get(k, []) for k in SCHEMA}, SCHEMA)
        state = self.state()
        self.audit(state, actor, "dataset_update", detail)
        atomic_write(self.root / "state.xlsx", state)

    def version(self, ident):
        if not ident or len(ident) != 24 or any(c not in "0123456789abcdef" for c in ident):
            return None
        path = self.root / "versions" / (ident + ".xlsx")
        return read_tables(path) if path.exists() else None

    def published_id(self):
        return next((r["value"] for r in self.state().get("Meta", []) if r["key"] == "published"), "")

    def save_draft(self, result, data, actor, fingerprint):
        ident = secrets.token_hex(12)
        tables = {"Schedule": result["schedule"], "Penalties": result.get("penalties", []),
                  "Meta": [dict(key=k, value=v) for k,v in {"id":ident, "status":result["status"], "score":result.get("score",0),
                  "created_at":stamp(), "created_by":actor,"fingerprint":fingerprint,"state":"draft","method":result.get("method","CP-SAT optimization")}.items()],
                  "Attendees": [], "People": data["People"], "Enrollments":data["Enrollments"]}
        for row in result["schedule"]:
            for member in data["Enrollments"]:
                if member["class_id"] == row["class_id"]:
                    tables["Attendees"].append(dict(session_id=row["session_id"], person_id=member["person_id"],role="student"))
            for field, role in [("teacher_id","teacher"),("assistant_ids","assistant"),("key_coach_id","key_coach")]:
                for pid in text(row.get(field)).split("|"):
                    if pid:
                        tables["Attendees"].append(dict(session_id=row["session_id"],person_id=pid,role=role))
        atomic_write(self.root / "versions" / (ident+".xlsx"), tables)
        state = self.state()
        self.audit(state,actor,"draft_created",ident)
        atomic_write(self.root / "state.xlsx",state)
        return ident

    def publish(self, ident, actor):
        from .solver import validate_solution
        version = self.version(ident)
        if not version:
            raise ValueError("Không tìm thấy phiên bản.")
        meta = {r["key"]:r["value"] for r in version["Meta"]}
        if meta.get("fingerprint") != self.fingerprint():
            raise ValueError("Dữ liệu/cấu hình đã đổi. Cần chạy CP-SAT và duyệt nháp mới.")
        errors=validate_solution(self.data(),version["Schedule"])
        if errors:
            raise ValueError("Kiểm tra trước công bố không đạt: "+errors[0]["message"])
        state=self.state()
        for row in state["Meta"]:
            if row["key"]=="published":
                row["value"]=ident
        self.audit(state,actor,"published",ident)
        atomic_write(self.root / "state.xlsx",state)
        # Published assignments become the next optimization baseline (SC-01).
        data=self.data()
        schedule={r["session_id"]:r for r in version["Schedule"]}
        for row in data["Sessions"]:
            assigned=schedule[row["session_id"]]
            for target,source in [("baseline_slot","slot_id"),("baseline_teacher","teacher_id"),("baseline_room","room_id"),("baseline_assistants","assistant_ids"),("baseline_key_coach","key_coach_id")]:
                row[target]=assigned.get(source,"")
        atomic_write(self.root / "dataset.xlsx",data,SCHEMA)
