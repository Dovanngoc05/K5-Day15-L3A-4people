"""Excel-backed scheduling web app. Start with python run.py."""
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

from filelock import FileLock, Timeout
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from waitress import serve

from .schedule_excel import FILES, LIMIT, SCHEMA, clean, draft, open_excel, write_book
from .schedule_solver import solve

ROOT = Path(__file__).resolve().parents[1]
EDITOR_FILE = "ClassesesData.xlsx"
EDITOR_SHEETS = {
    "Classes": ("Buổi học", "Điền nhóm tham dự và số Lab Coach, Key Coach cần có. Điền 0 nếu không cần. Dùng locked=1 để khóa phương án hiện tại."),
    "Slots": ("Giờ và phòng", "Điền phòng và sức chứa đã xác nhận. Thêm dòng với slot_id mới nếu buổi có phương án khác. Dùng YYYY-MM-DD và HH:MM."),
    "Teachers": ("Giảng viên", "Điền danh sách chuyên đề trong skills và giới hạn phút làm việc theo ngày, tuần."),
    "TeacherAvailability": ("Giờ rảnh giảng viên", "Điền một dòng cho mỗi khoảng rảnh. preferred=1 là giờ mong muốn, 0 là giờ rảnh bình thường."),
    "Coaches": ("Coach", "Điền vai trò lab, key hoặc lab;key, chuyên đề phù hợp và giới hạn phút theo ngày, tuần."),
    "CoachAvailability": ("Giờ rảnh coach", "Dùng tên từ bảng Coach. Điền ngày, giờ bắt đầu, giờ kết thúc và preferred (0 hoặc 1)."),
    "Learners": ("Học viên", "Điền một nhóm cho mỗi học viên. Tên nhóm phải khớp với nhóm tham dự trong bảng Buổi học."),
    "LearnerAvailability": ("Giờ rảnh học viên", "Dùng mã học viên hoặc group:TênNhóm để nhập giờ rảnh cho cả nhóm. Dòng riêng của học viên được ưu tiên trong cùng ngày."),
    "SourceHints": ("Đối chiếu lịch gốc", "Xem chi tiết được trích từ workbook gốc khi cần xác nhận phân công hoặc giờ học."),
}


def replace_file(path, payload):
    pending = path.with_name(f"{uuid4().hex}.pending")
    try:
        pending.write_bytes(payload)
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def read_editor(payload):
    workbook = open_excel(payload, uploaded=False)
    try:
        return {sheet.title: list(sheet.values) for sheet in workbook}
    finally:
        workbook.close()


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


def publish(storage, source, workbook, students, result):
    generation = uuid4().hex
    folder = storage / generation
    folder.mkdir()
    for name in FILES:
        (folder / name).write_bytes((source / name).read_bytes())
    (folder / EDITOR_FILE).write_bytes(workbook)
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
                      MAX_FORM_PARTS=12, MAX_FORM_MEMORY_SIZE=8 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      SESSION_COOKIE_SECURE=os.environ.get("SCHEDULE_HTTPS") == "1")
    app.jinja_env.filters["clock"] = clock

    def published():
        pointer = storage / "current"
        if not pointer.is_file():
            return {}, {}
        generation = pointer.read_text(encoding="ascii")
        return read_published(storage / generation / "published.xlsx")

    def working_folder():
        pointer = storage / "working"
        try:
            return storage / pointer.read_text(encoding="ascii")
        except FileNotFoundError:
            return None

    lock = FileLock(storage / "publish.lock", timeout=2)

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
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
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
                elif action == "import":
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
                        workbook = write_book(draft(books))
                    with lock:
                        generation = uuid4().hex
                        folder = storage / generation
                        folder.mkdir()
                        for name, payload in zip(FILES, payloads):
                            (folder / name).write_bytes(payload)
                        (folder / EDITOR_FILE).write_bytes(workbook)
                        replace_file(storage / "working", generation.encode("ascii"))
                    flash("Đã nhập dữ liệu. Bổ sung các ô còn thiếu và lưu từng bảng trước khi xếp lịch.")
                    return redirect(url_for("edit", sheet="Classes"))
                elif action in {"check", "publish"}:
                    with lock:
                        source = working_folder()
                        if source is None:
                            raise ValueError("Hãy nhập ba tệp Excel gốc trước.")
                        workbook = (source / EDITOR_FILE).read_bytes()
                        book = open_excel(workbook, uploaded=False)
                        try:
                            students, current = published()
                            roster, result, status, score = solve((book, book, book), current)
                        finally:
                            book.close()
                        if action == "publish":
                            publish(storage, source, workbook, roster, result)
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
                               student_count=len(students), files=FILES, imported=working_folder() is not None)

    @app.route("/admin/data/<sheet>", methods=["GET", "POST"])
    @require("admin")
    def edit(sheet):
        if sheet not in EDITOR_SHEETS:
            abort(404)
        folder = working_folder()
        if folder is None:
            return redirect(url_for("admin"))
        payload = (folder / EDITOR_FILE).read_bytes()
        version = sha256(payload).hexdigest()
        tables = read_editor(payload)
        columns, *entries = tables[sheet]
        entries = [[value if value is not None else "" for value in row] for row in entries]
        if request.method == "POST":
            if sheet not in SCHEMA:
                abort(405)
            values = [request.form.getlist(f"col{idx}") for idx in range(len(columns))]
            if len({len(column) for column in values}) != 1 or len(values[0]) > 19999:
                abort(400)
            entries = list(zip(*values))
            try:
                clean_rows = []
                for number, row in enumerate(entries, 2):
                    try:
                        cleaned = tuple(clean(value) for value in row)
                    except ValueError as error:
                        raise ValueError(f"Dòng {number}. {error}") from error
                    if any(cleaned):
                        clean_rows.append(cleaned)
                updated = write_book([(name, table[0], clean_rows if name == sheet else table[1:])
                                      for name, table in tables.items()])
                with lock:
                    latest = working_folder()
                    if (latest != folder or request.form.get("generation") != folder.name
                            or request.form.get("version") != sha256((folder / EDITOR_FILE).read_bytes()).hexdigest()):
                        flash("Dữ liệu đã thay đổi trong phiên khác. Bảng đang hiển thị dữ liệu mới nhất.")
                        return redirect(url_for("edit", sheet=sheet))
                    checked = open_excel(updated, uploaded=False)
                    checked.close()
                    replace_file(folder / EDITOR_FILE, updated)
                flash(f"Đã lưu bảng {EDITOR_SHEETS[sheet][0]} vào {EDITOR_FILE}.")
                return redirect(url_for("edit", sheet=sheet))
            except (ValueError, Timeout) as error:
                flash(str(error) if isinstance(error, ValueError) else "Dữ liệu đang được cập nhật. Vui lòng thử lại.")
        return render_template("schedule.html", page="editor", sheet=sheet, sheets=EDITOR_SHEETS,
                               rows=entries, columns=columns, version=version, generation=folder.name,
                               editable=sheet in SCHEMA, workbook_name=EDITOR_FILE)

    @app.get("/admin/data-file")
    @require("admin")
    def download_data():
        folder = working_folder()
        if folder is None:
            abort(404)
        return send_file(BytesIO((folder / EDITOR_FILE).read_bytes()), as_attachment=True,
                         download_name=EDITOR_FILE)

    return app


def ordered(items):
    return sorted(items, key=lambda entry: (entry[1]["day"], entry[1]["start"], entry[0]))


if __name__ == "__main__":
    try:
        application = create_app()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    host = os.environ.get("SCHEDULE_HOST", "127.0.0.1")
    port = int(os.environ.get("SCHEDULE_PORT", "8080"))
    if not application.config["SESSION_COOKIE_SECURE"]:
        print(f"Lịch đào tạo AI20K · http://{host}:{port}", flush=True)
    serve(application, host=host, port=port)
