"""Flask UI; identities and all data are stored in local Excel workbooks."""
from datetime import timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path
import hashlib
import hmac
import os
import re
import secrets
import time

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .demo import demo_data
from .excel import SCHEMA, atomic_write, empty_data, read_tables, text, workbook_bytes
from ..ai import llama_model_paths
from .extraction_job import ExtractionJob
from .importer import combine_import, import_workbook
from .security import inspect_xlsx, scan_payload, scanner_command
from .solver import readiness, solve
from .store import Store, stamp
from .teacher_profiles import REPORT_NAME, fill_report_profiles


def create_app(root=None):
    app=Flask(__name__)
    storage=Store(root or os.environ.get("A5_DATA_DIR", "runtime"))
    extraction=ExtractionJob(storage.root, app.logger)
    secret=storage.root/"session.key"
    if not secret.exists():
        try:
            with secret.open("x",encoding="ascii") as out:
                out.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app.config.update(SECRET_KEY=secret.read_text(encoding="ascii"), MAX_CONTENT_LENGTH=32*1024*1024,
        MAX_FORM_MEMORY_SIZE=100_000, MAX_FORM_PARTS=40, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=os.environ.get("A5_HTTPS")=="1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2), STORE=storage)
    failures={}

    def current():
        uid=session.get("uid")
        if not uid:
            return None
        return next((a for a in storage.state().get("Accounts",[]) if a.get("username")==uid),None)

    def require(role=None):
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args,**kwargs):
                if not g.user:
                    return redirect(url_for("login"))
                if role and g.user.get("role")!=role:
                    abort(403)
                return fn(*args,**kwargs)
            return wrapper
        return decorator

    @app.before_request
    def protect():
        g.user=current()
        if "csrf" not in session:
            session["csrf"]=secrets.token_urlsafe(32)
        if request.method=="POST":
            value=request.form.get("csrf","")
            if not hmac.compare_digest(value,session["csrf"]):
                abort(400,description="Phiên xác nhận không hợp lệ. Tải lại trang rồi thử lại.")

    @app.after_request
    def headers(response):
        response.headers["Content-Security-Policy"]="default-src 'self'; style-src 'self'; img-src 'self' data:; script-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Cache-Control"]="no-store"
        return response

    @app.context_processor
    def context():
        scenario=storage.state().get("Scenario",[])
        return dict(user=getattr(g,"user",None),csrf=session.get("csrf",""),scenario=scenario[0] if scenario else None)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error(exc):
        return render_template("error.html",message=exc.description,code=exc.code),exc.code

    @app.route("/")
    def index():
        return redirect(url_for("admin" if g.user and g.user["role"]=="admin" else "personal" if g.user else "login"))

    @app.route("/login",methods=["GET","POST"])
    def login():
        if request.method=="POST":
            username=request.form.get("username","").strip()[:80]
            key=(request.remote_addr,username)
            now=time.monotonic()
            failures[key]=[t for t in failures.get(key,[]) if now-t<300]
            ip_key=(request.remote_addr,"*")
            failures[ip_key]=[t for t in failures.get(ip_key,[]) if now-t<300]
            if len(failures[key])>=5 or len(failures[ip_key])>=20:
                flash("Quá nhiều lần đăng nhập thất bại. Thử lại sau 5 phút.","error")
                return render_template("login.html"),429
            account=next((a for a in storage.state().get("Accounts",[]) if a.get("username")==username),None)
            password=request.form.get("password","")
            if account and len(password)<=256 and check_password_hash(account["password_hash"],password):
                session.clear()
                session["uid"]=account["username"]
                session["csrf"]=secrets.token_urlsafe(32)
                session.permanent=True
                return redirect(url_for("index"))
            failures[key].append(now)
            failures[ip_key].append(now)
            flash("Tài khoản hoặc mật khẩu không đúng.","error")
        no_admin=not any(a.get("role")=="admin" for a in storage.state().get("Accounts",[]))
        return render_template("login.html",no_admin=no_admin)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/admin")
    @require("admin")
    def admin():
        with storage.lock:
            data=storage.data()
            problems=readiness(data)
            state=storage.state()
            published=storage.published_id()
            revisions=[]
            for p in sorted((storage.root/"versions").glob("*.xlsx"),key=lambda p:p.stat().st_mtime,reverse=True) if (storage.root/"versions").exists() else []:
                ver=storage.version(p.stem)
                meta={r["key"]:r["value"] for r in ver["Meta"]}
                revisions.append(meta)
        job=extraction.snapshot()
        return render_template("admin.html",data=data,problems=problems[:100],problem_count=len(problems),
            scanner=scanner_command()[0],revisions=revisions[:20],published=published,
            audit=list(reversed(state.get("Audit",[])))[:15],accounts=state.get("Accounts",[]),
            extraction_job=job if job and job["owner"]==g.user["username"] else None)

    @app.post("/admin/demo")
    @require("admin")
    def demo():
        with storage.lock:
            if storage.data().get("Sessions") or storage.data().get("People"):
                flash("Chỉ nạp mẫu vào kho trống để tránh ghi đè dữ liệu. Dùng A5_DATA_DIR khác để thử mẫu.","error")
            else:
                storage.save_data(demo_data(),g.user["username"],"Nạp dữ liệu hoàn toàn giả lập, không phải dữ liệu vận hành thật")
                flash("Đã nạp dữ liệu mẫu giả lập đầy đủ để chạy CP-SAT.","success")
        return redirect(url_for("admin"))

    @app.get("/admin/template")
    @require("admin")
    def template():
        with storage.lock:
            data=storage.data()
            assumptions=storage.state().get("Assumptions",[])
            if assumptions:
                data["Assumptions"]=assumptions
        return send_file(BytesIO(workbook_bytes(data,SCHEMA)),download_name="a5-input.xlsx",as_attachment=True,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.post("/admin/extraction")
    @require("admin")
    def start_extraction():
        try:
            executable, model = llama_model_paths()
            files = request.files.getlist("files")
            if len(files) != 2:
                raise ValueError("Chọn đúng hai workbook: lịch giảng dạy và lịch Lab Coach.")
            workbooks = []
            for file in files:
                payload = file.read(10 * 1024 * 1024 + 1)
                workbooks.append((inspect_xlsx(file.filename, payload), payload))
            ident = extraction.start(g.user["username"], workbooks, executable, model)
        except Exception as exc:
            app.logger.warning("Extraction start blocked: %s", type(exc).__name__)
            flash(safe_message(exc), "error")
            return redirect(url_for("admin"))
        return redirect(url_for("extraction_status", ident=ident), code=303)

    def own_extraction(ident):
        job = extraction.snapshot()
        if not job or job["id"] != ident or job["owner"] != g.user["username"]:
            abort(404)
        return job

    @app.get("/admin/extraction/<ident>")
    @require("admin")
    def extraction_status(ident):
        return render_template("extraction.html", job=own_extraction(ident))

    @app.get("/admin/extraction/<ident>/report")
    @require("admin")
    def extraction_report(ident):
        if own_extraction(ident)["status"] != "done":
            abort(404)
        return send_file(extraction.report_path(ident), as_attachment=True,
                         download_name="schedule-extraction.json", mimetype="application/json")

    @app.post("/admin/upload")
    @require("admin")
    def upload():
        files=request.files.getlist("files")
        if not 1<=len(files)<=10:
            flash("Mỗi lần chọn từ 1 đến 10 file .xlsx.","error")
            return redirect(url_for("admin"))
        try:
            imports=[]
            notes=[]
            manifests=[]
            room_evidence=[]
            for file in files:
                payload=file.read(10*1024*1024+1)
                name=inspect_xlsx(file.filename,payload)
                engine=scan_payload(payload)
                evidence=[]
                tables,messages=import_workbook(payload,room_evidence=evidence)
                source_id=secrets.token_hex(12)
                room_evidence.extend(dict(file=name,source_id=source_id,**row) for row in evidence)
                source_folder=storage.root/"uploads"
                source_folder.mkdir(parents=True,exist_ok=True)
                (source_folder/(source_id+".xlsx")).write_bytes(payload)
                # Canonical detection uses exact sheet names, not file names.
                book_names=set(read_sheet_names(payload))
                imports.append((tables,bool(book_names & set(SCHEMA))))
                notes.extend(name+": "+m for m in messages)
                manifests.append(dict(file=name,source_id=source_id,sha256=hashlib.sha256(payload).hexdigest(),scanner=engine,scanned_at=stamp()))
            with storage.lock:
                before=storage.fingerprint()
                current_data=storage.data()
                result=combine_import(current_data,imports)
                profiles=fill_report_profiles(storage.root / REPORT_NAME,result)
                if profiles:
                    notes.append(f"{REPORT_NAME}: bổ sung thông tin còn thiếu cho {len(profiles)} hồ sơ giảng dạy theo mã người.")
                guard_locked(current_data,result)
                ident=secrets.token_hex(12)
                pending=result | {"_Notes":[dict(message=m) for m in notes],"_Manifest":manifests,
                    "_Meta":[dict(key="base",value=before),dict(key="actor",value=g.user["username"])]}
                if profiles:
                    pending["_Profiles"]=profiles
                if room_evidence:
                    pending["_LabRoomEvidence"]=room_evidence
                atomic_write(storage.root/"pending"/(ident+".xlsx"),pending)
                session["pending"]=ident
            return redirect(url_for("preview_upload"))
        except Exception as exc:
            app.logger.warning("Import blocked: %s",type(exc).__name__)
            flash("Không nhập file: "+safe_message(exc),"error")
            return redirect(url_for("admin"))

    def pending_file():
        ident=session.get("pending","")
        if not re.fullmatch(r"[0-9a-f]{24}",ident):
            abort(404)
        path=storage.root/"pending"/(ident+".xlsx")
        if not path.exists():
            abort(404)
        tables=read_tables(path)
        meta={r["key"]:r["value"] for r in tables["_Meta"]}
        if meta["actor"]!=g.user["username"]:
            abort(403)
        return path,tables,meta

    @app.get("/admin/upload-preview")
    @require("admin")
    def preview_upload():
        _,tables,_=pending_file()
        return render_template("import.html",tables=tables,problems=readiness(tables)[:100])

    @app.post("/admin/upload-confirm")
    @require("admin")
    def confirm_upload():
        try:
            with storage.lock:
                path,tables,meta=pending_file()
                if meta["base"]!=storage.fingerprint():
                    raise ValueError("Dữ liệu đã đổi sau bản xem trước. Upload lại để đối chiếu.")
                guard_locked(storage.data(),tables)
                storage.save_data(tables,g.user["username"],"Admin xác nhận nhập: "+"; ".join(r["file"]+" sha256="+r["sha256"]+" scanner="+r["scanner"] for r in tables["_Manifest"]))
                state=storage.state()
                state.setdefault("Sources",[]).extend(tables["_Manifest"])
                state.setdefault("SourceNotes",[]).extend(dict(import_id=path.stem,actor=g.user["username"],message=r["message"]) for r in tables["_Notes"])
                if tables.get("_LabRoomEvidence"):
                    state.setdefault("LabRoomEvidence",[]).extend(
                        dict(import_id=path.stem,**row) for row in tables["_LabRoomEvidence"])
                atomic_write(storage.root/"state.xlsx",state)
                path.unlink()
                session.pop("pending",None)
            flash("Đã nhập dữ liệu. Xem báo cáo thiếu/đủ trước khi xếp lịch.","success")
        except ValueError as exc:
            flash(str(exc),"error")
        return redirect(url_for("admin"))

    @app.post("/admin/weights")
    @require("admin")
    def weights():
        try:
            values=[]
            for i in range(1,8):
                code=f"SC-{i:02}"
                value=int(request.form[code])
                if not 0<=value<=10000:
                    raise ValueError("Trọng số phải từ 0 đến 10.000")
                values.append(dict(constraint_id=code,weight=value))
            with storage.lock:
                data=storage.data()
                data["Weights"]=values
                storage.save_data(data,g.user["username"],"Đổi trọng số SC; các nháp cũ cần tính lại")
            flash("Đã lưu trọng số.","success")
        except (ValueError,KeyError):
            flash("Trọng số không hợp lệ.","error")
        return redirect(url_for("admin"))

    @app.post("/admin/solve")
    @require("admin")
    def run_solver():
        with storage.lock:
            data=storage.data()
            fingerprint=storage.fingerprint()
        try:
            result=solve(data)
            if not result["schedule"]:
                flash(result["status"]+": "+"; ".join(e["message"] for e in result["errors"][:4]),"error")
                return redirect(url_for("admin"))
            with storage.lock:
                if fingerprint!=storage.fingerprint():
                    raise ValueError("Dữ liệu thay đổi khi solver đang chạy. Chạy lại.")
                ident=storage.save_draft(result,data,g.user["username"],fingerprint)
            return redirect(url_for("version",ident=ident))
        except ValueError as exc:
            flash(str(exc),"error")
            return redirect(url_for("admin"))

    @app.get("/admin/versions/<ident>")
    @require("admin")
    def version(ident):
        with storage.lock:
            tables=storage.version(ident)
            if not tables:
                abort(404)
            meta={r["key"]:r["value"] for r in tables["Meta"]}
            published=storage.version(storage.published_id())
        old={r["session_id"]:r for r in (published or {}).get("Schedule",[])}
        changed=[r["session_id"] for r in tables["Schedule"] if old.get(r["session_id"])!=r]
        return render_template("version.html",tables=tables,meta=meta,changed=changed,ident=ident)

    @app.post("/admin/versions/<ident>/publish")
    @require("admin")
    def publish(ident):
        try:
            with storage.lock:
                storage.publish(ident,g.user["username"])
            flash("Đã công bố lịch trong app. Học viên chỉ thấy các buổi của bản thân.","success")
        except ValueError as exc:
            flash(str(exc),"error")
        return redirect(url_for("admin"))

    @app.post("/admin/lock")
    @require("admin")
    def lock_session():
        sid=request.form.get("session_id","")
        reason=request.form.get("reason","").strip()
        if not 5<=len(reason)<=500:
            flash("Cần lý do 5–500 ký tự.","error")
            return redirect(url_for("admin"))
        with storage.lock:
            data=storage.data()
            row=next((r for r in data["Sessions"] if r["session_id"]==sid),None)
            if row is None:
                abort(404)
            if request.form.get("action")=="unlock":
                row["locked"]="0"
            else:
                current=storage.version(storage.published_id())
                chosen=next((r for r in (current or {}).get("Schedule",[]) if r["session_id"]==sid),None)
                if not chosen:
                    flash("Cần một lịch đã công bố cho buổi này trước khi khoá.","error")
                    return redirect(url_for("admin"))
                row["locked"]="1"
                copy_baseline(row,chosen)
            storage.save_data(data,g.user["username"],request.form.get("action", "lock")+" "+sid+": "+reason)
        flash("Đã cập nhật trạng thái khoá; nháp cũ cần tính lại.","success")
        return redirect(url_for("admin"))

    @app.post("/admin/accounts")
    @require("admin")
    def accounts():
        try:
            username=request.form.get("username","").strip()
            password=request.form.get("password","")
            pid=request.form.get("person_id","").strip()
            with storage.lock:
                people={p["person_id"] for p in storage.data()["People"]}
                if pid not in people:
                    raise ValueError("Chọn đúng mã người từ bảng People.")
                add_account(storage,username,password,"student",pid,g.user["username"])
            flash("Đã tạo tài khoản cá nhân. Mật khẩu được lưu dạng hash.","success")
        except ValueError as exc:
            flash(str(exc),"error")
        return redirect(url_for("admin"))

    @app.get("/student")
    @require()
    def personal():
        if g.user["role"]=="admin":
            return redirect(url_for("admin"))
        with storage.lock:
            tables=storage.version(storage.published_id())
        pid=g.user.get("person_id")
        allowed={r["session_id"] for r in (tables or {}).get("Attendees",[]) if r["person_id"]==pid}
        rows=[r for r in (tables or {}).get("Schedule",[]) if r["session_id"] in allowed]
        # No client-supplied person ID is used to select records.
        day=request.args.get("date","")
        if day:
            rows=[r for r in rows if r["date"]==day]
        rows=sorted(rows,key=lambda r:(r["date"],r["start"]))
        meta={r["key"]:r["value"] for r in (tables or {}).get("Meta",[])}
        return render_template("student.html",rows=rows,person_id=pid,day=day,meta=meta)

    from .setup import register_setup
    register_setup(app,storage,require)
    return app


def read_sheet_names(payload):
    from openpyxl import load_workbook
    book=load_workbook(BytesIO(payload),read_only=True)
    try:
        return book.sheetnames
    finally:
        book.close()


def safe_message(exc):
    if isinstance(exc,ValueError):
        return str(exc)[:1200]
    return "File không hợp lệ hoặc thao tác không hoàn tất. Kiểm tra định dạng Excel và trình quét."


def guard_locked(current,new):
    incoming={r.get("session_id"):r for r in new.get("Sessions",[])}
    old_slots={r.get("slot_id"):r for r in current.get("Slots",[])}
    new_slots={r.get("slot_id"):r for r in new.get("Slots",[])}
    for row in current.get("Sessions",[]):
        candidate=incoming.get(row["session_id"])
        same=candidate is not None and all(text(row.get(key))==text(candidate.get(key)) for key in SCHEMA["Sessions"])
        if text(row.get("locked"))=="1" and not same:
            raise ValueError("HC-10: không thay/xoá buổi đang khoá "+row["session_id"]+". Admin phải mở khoá có lý do trước.")
        if text(row.get("locked"))=="1" and old_slots.get(row.get("baseline_slot"))!=new_slots.get(row.get("baseline_slot")):
            raise ValueError("HC-10: không đổi giờ/ngày của khung thuộc lịch khoá "+row["session_id"])


def copy_baseline(target,scheduled):
    for dest,source in [("baseline_slot","slot_id"),("baseline_teacher","teacher_id"),("baseline_assistants","assistant_ids"),("baseline_key_coach","key_coach_id"),("baseline_room","room_id")]:
        target[dest]=scheduled.get(source,"")


def add_account(storage,username,password,role,person_id,actor):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}",username):
        raise ValueError("Tài khoản gồm 3–64 chữ/số hoặc . _ -")
    if not 12<=len(password)<=256:
        raise ValueError("Mật khẩu phải từ 12 đến 256 ký tự.")
    state=storage.state()
    if any(a["username"]==username for a in state.get("Accounts",[])):
        raise ValueError("Tên tài khoản đã tồn tại.")
    state.setdefault("Accounts",[]).append(dict(username=username,password_hash=generate_password_hash(password),role=role,person_id=person_id))
    storage.audit(state,actor,"account_created",username)
    atomic_write(storage.root/"state.xlsx",state)
