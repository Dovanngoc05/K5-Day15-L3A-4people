"""Excel-backed scheduling web app. Start with python -m codebase.schedule_web."""
from collections import defaultdict
from contextlib import ExitStack
from datetime import timedelta
from functools import wraps
from hashlib import sha256
import hmac
from io import BytesIO
import os
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
from zipfile import ZipFile

from filelock import FileLock, Timeout
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from waitress import serve

from .schedule_excel import FILES, LIMIT, clean, draft, open_excel, write_book
from .schedule_solver import solve

ROOT = Path(__file__).resolve().parents[1]


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def read_published(path):
    if not path.exists():
        return {}, {}
    workbook = open_excel(path.read_bytes(), uploaded=False)
    try:
        students = {}
        members = defaultdict(list)
        for sid, name, group in list(workbook["Students"].values)[1:]:
            students[sid] = name
            members[group].append(sid)
        result = {}
        for row in list(workbook["Schedule"].values)[1:]:
            cid, subject, slot, day, start, end, rooms, teacher, lab, key, locked, lab_count, key_count, groups = row
            lab, key = tuple((lab or "").splitlines()), tuple((key or "").splitlines())
            result[cid] = dict(subject=subject, slot=slot, day=day, start=start, end=end,
                               rooms=tuple(rooms.splitlines()), teacher=teacher, lab=lab, key=key,
                               coaches=lab + key, locked=locked, lab_count=lab_count, key_count=key_count,
                               students=tuple(sorted(sid for group in groups.splitlines() for sid in members[group])))
        return students, result
    finally:
        workbook.close()


def publish(storage, payloads, students, result):
    generation = uuid4().hex
    folder = storage / generation
    folder.mkdir()
    for name, payload in zip(FILES, payloads):
        (folder / name).write_bytes(payload)
    schedule = [(cid, row["subject"], row["slot"], row["day"], row["start"], row["end"],
                 "\n".join(row["rooms"]), row["teacher"], "\n".join(row["lab"]), "\n".join(row["key"]),
                 row["locked"], row["lab_count"], row["key_count"], "\n".join(row["groups"])) for cid, row in result.items()]
    (folder / "published.xlsx").write_bytes(write_book([
        ("Schedule", "class_id subject slot day start end rooms teacher lab key locked lab_count key_count groups".split(), schedule),
        ("Students", ["student_id", "full_name", "group"],
         [(sid, row["full_name"], row["group"]) for sid, row in students.items()]),
    ]))
    pointer = storage / f"{generation}.pending"
    pointer.write_text(generation, encoding="ascii")
    pointer.replace(storage / "current")


def create_app(storage=None, *, secret=None, admin_password=None):
    app = Flask(__name__)
    storage = Path(storage or ROOT / ".schedule-data")
    storage.mkdir(parents=True, exist_ok=True)
    secret = secret or os.environ.get("SCHEDULE_SECRET", "")
    admin_password = admin_password or os.environ.get("SCHEDULE_ADMIN_PASSWORD", "")
    if len(secret) < 32 or len(admin_password) < 16:
        raise RuntimeError("Cần SCHEDULE_SECRET (ít nhất 32 ký tự) và SCHEDULE_ADMIN_PASSWORD (ít nhất 16 ký tự).")
    app.config.update(SECRET_KEY=secret, MAX_CONTENT_LENGTH=3 * LIMIT + 65536,
                      MAX_FORM_PARTS=12, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      SESSION_COOKIE_SECURE=os.environ.get("SCHEDULE_HTTPS") == "1")
    app.jinja_env.filters["clock"] = clock

    def published():
        pointer = storage / "current"
        if not pointer.is_file():
            return {}, {}
        generation = pointer.read_text(encoding="ascii")
        return read_published(storage / generation / "published.xlsx")

    def student_code(sid):
        return hmac.new(secret.encode(), ("student-login:" + sid).encode(), sha256).hexdigest()[:40]

    def same(a, b):
        return hmac.compare_digest(a.encode(), b.encode())

    def require(role):
        def decorator(view):
            @wraps(view)
            def restricted(*args, **kwargs):
                if not session.get("role"):
                    return redirect(url_for("login"))
                if session["role"] != role:
                    abort(403)
                return view(*args, **kwargs)
            return restricted
        return decorator

    @app.before_request
    def csrf():
        if "csrf" not in session:
            session["csrf"] = token_urlsafe(24)
        if request.method == "POST" and not same(request.form.get("csrf", ""), session["csrf"]):
            abort(400)

    @app.after_request
    def headers(response):
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    @app.errorhandler(413)
    def too_large(_):
        return render_template("schedule.html", page="error", message="Tổng dung lượng tải lên vượt giới hạn."), 413

    @app.get("/")
    def home():
        return redirect(url_for({"admin": "admin", "student": "student"}.get(session.get("role"), "login")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            role = request.form.get("role")
            password = request.form.get("password", "")
            try:
                sid = clean(request.form.get("student_id", ""))
            except ValueError:
                sid = ""
            valid = len(password) <= 512 and (
                (role == "admin" and same(password, admin_password))
                or (role == "student" and sid and same(password, student_code(sid)) and sid in published()[0]))
            if valid:
                session.clear()
                session.update(role=role, sid=sid if role == "student" else "", csrf=token_urlsafe(24))
                session.permanent = True
                return redirect(url_for("home"))
            flash("Thông tin đăng nhập không hợp lệ.")
        return render_template("schedule.html", page="login")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/student")
    @require("student")
    def student():
        students, result = published()
        sid = session["sid"]
        if sid not in students:
            session.clear()
            return redirect(url_for("login"))
        personal = [(cid, row) for cid, row in result.items() if sid in row["students"]]
        return render_template("schedule.html", page="student", name=students[sid], schedule=ordered(personal))

    @app.route("/admin", methods=["GET", "POST"])
    @require("admin")
    def admin():
        students, current = published()
        preview = None
        issued = None
        status = score = None
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "issue":
                    sid = clean(request.form.get("student_id", ""))
                    if sid not in students:
                        raise ValueError("Mã học viên chưa có trong lịch đã công bố.")
                    issued = (sid, student_code(sid))
                elif action in {"draft", "check", "publish"}:
                    uploads = [request.files.get(f"file{index}") for index in range(3)]
                    if any(not upload or Path(upload.filename).suffix.lower() != ".xlsx" for upload in uploads):
                        raise ValueError("Hãy tải đủ ba tệp .xlsx đúng vị trí.")
                    payloads = [upload.stream.read(LIMIT + 1) for upload in uploads]
                    with ExitStack() as resources:
                        books = []
                        for name, payload in zip(FILES, payloads):
                            try:
                                book = open_excel(payload)
                            except ValueError as error:
                                raise ValueError(f"{name} · {error}") from error
                            resources.callback(book.close)
                            books.append(book)
                        if action == "draft":
                            target = BytesIO()
                            with ZipFile(target, "w") as archive:
                                for name, payload in zip(FILES, draft(books)):
                                    archive.writestr(name, payload)
                            target.seek(0)
                            return send_file(target, as_attachment=True, download_name="lich-nhap.zip", mimetype="application/zip")
                        with FileLock(storage / "publish.lock", timeout=2):
                            students, current = published()
                            roster, result, status, score = solve(books, current)
                            if action == "publish":
                                publish(storage, payloads, roster, result)
                                flash(f"Đã công bố {len(result)} buổi cho {len(roster)} học viên. {status} · {score} điểm phạt.")
                                return redirect(url_for("admin"))
                            preview = ordered(result.items())
                else:
                    abort(400)
            except (ValueError, Timeout) as error:
                flash(str(error) if isinstance(error, ValueError) else "Đang có lượt xếp lịch khác. Vui lòng thử lại.")
        try:
            person = clean(request.args.get("person", ""))
        except ValueError:
            abort(400)
        displayed = [(cid, row) for cid, row in current.items()
                     if not person or person in (row["teacher"], *row["coaches"]) or person in row["students"]]
        return render_template("schedule.html", page="admin", schedule=ordered(displayed),
                               class_count=len(current), person=person,
                               preview=preview, status=status, score=score, issued=issued,
                               student_count=len(students), files=FILES)

    return app


def ordered(items):
    return sorted(items, key=lambda entry: (entry[1]["day"], entry[1]["start"], entry[0]))


if __name__ == "__main__":
    serve(create_app(), host=os.environ.get("SCHEDULE_HOST", "127.0.0.1"),
          port=int(os.environ.get("SCHEDULE_PORT", "8080")))
