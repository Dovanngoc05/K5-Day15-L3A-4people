"""Admin-only explicit declarations for missing data; all changes audited."""
import re
from flask import flash, g, redirect, render_template, request, url_for
from .excel import text


def register_setup(app,store,require):
    @app.route("/admin/setup",methods=["GET","POST"])
    @require("admin")
    def setup_data():
        if request.method=="POST":
            try:
                with store.lock:
                    data=store.data()
                    people={p["person_id"]:p for p in data["People"]}
                    action=request.form.get("action")
                    if action=="person":
                        pid=request.form.get("person_id","")
                        if pid not in people:
                            raise ValueError("Không tìm thấy người.")
                        role=request.form.get("role")
                        if role not in {"teacher","assistant","key_coach","student"}:
                            raise ValueError("Vai trò không hợp lệ.")
                        day=int(request.form.get("max_minutes_day",""))
                        week=int(request.form.get("max_minutes_week",""))
                        if not 1<=day<=1440 or not 1<=week<=10080:
                            raise ValueError("Giới hạn giờ làm không hợp lệ.")
                        people[pid].update(role=role,subjects=request.form.get("subjects","").strip()[:2000],skills=request.form.get("skills","").strip()[:2000],max_minutes_day=day,max_minutes_week=week)
                        detail="Admin khai báo vai trò/chuyên môn/kỹ năng/giới hạn giờ: "+pid
                    elif action=="enroll":
                        cls=request.form.get("class_id","")
                        if cls not in {s["class_id"] for s in data["Sessions"]}:
                            raise ValueError("Lớp không hợp lệ.")
                        ids=set(re.split(r"[\s,|]+",request.form.get("student_ids","").strip()))-{''}
                        if request.form.get("all_students")=="yes":
                            ids={p for p,r in people.items() if r["role"]=="student"}
                        if not ids or any(p not in people or people[p]["role"]!="student" for p in ids):
                            raise ValueError("Chỉ dùng mã học viên có trong People.")
                        existing={(r["person_id"],r["class_id"]) for r in data["Enrollments"]}
                        data["Enrollments"].extend(dict(person_id=p,class_id=cls) for p in sorted(ids) if (p,cls) not in existing)
                        detail=f"Admin xác nhận đăng ký {len(ids)} học viên vào {cls}"
                    elif action=="availability":
                        pid=request.form.get("person_id","")
                        ids=set(people) if pid=="ALL" else {pid}
                        if not ids or not ids<=people.keys():
                            raise ValueError("Mã người không hợp lệ.")
                        slot_ids=set(request.form.getlist("slot_ids"))
                        all_slots={s["slot_id"] for s in data["Slots"]}
                        if request.form.get("all_slots")=="yes":
                            slot_ids=all_slots
                        if not slot_ids or not slot_ids<=all_slots:
                            raise ValueError("Cần chọn khung giờ hợp lệ.")
                        if request.form.get("confirm")!="yes":
                            raise ValueError("Cần xác nhận khai báo giờ rảnh.")
                        available,preferred=request.form.get("available"),request.form.get("preferred")
                        if available not in {"0","1"} or preferred not in {"0","1"}:
                            raise ValueError("Giờ rảnh/ưu tiên phải là 0 hoặc 1.")
                        index={(r["person_id"],r["slot_id"]):r for r in data["Availability"]}
                        for person in ids:
                            for slot in slot_ids:
                                index[(person,slot)]=dict(person_id=person,slot_id=slot,available=available,preferred=preferred)
                        data["Availability"]=list(index.values())
                        detail=f"Admin khai báo giờ rảnh: {len(ids)} người, {len(slot_ids)} khung; available={available}, preferred={preferred}"
                    elif action=="sessions":
                        cls=request.form.get("class_id","")
                        rows=[s for s in data["Sessions"] if s["class_id"]==cls]
                        if not rows:
                            raise ValueError("Không có buổi trong lớp đã chọn.")
                        acount=int(request.form.get("assistant_count",""))
                        key=int(request.form.get("key_coach_required",""))
                        if not 0<=acount<=10 or key not in {0,1}:
                            raise ValueError("Số coach không hợp lệ.")
                        skill=request.form.get("required_skill","").strip()[:1000]
                        unlock=request.form.get("unlock")=="yes"
                        reason=request.form.get("reason","").strip()
                        if not 5<=len(reason)<=500:
                            raise ValueError("Cần lý do 5–500 ký tự.")
                        if any(text(s.get("locked"))=="1" for s in rows) and not unlock:
                            raise ValueError("Lớp có buổi khoá. Cần chủ động mở khoá trước khi thay đổi.")
                        for row in rows:
                            row.update(assistant_count=acount,key_coach_required=key,required_skill=skill)
                            if unlock:
                                row["locked"]="0"
                        detail=f"Admin đổi yêu cầu coach lớp {cls}; mở khoá={unlock}: {reason}"
                    else:
                        raise ValueError("Thao tác không hợp lệ.")
                    store.save_data(data,g.user["username"],detail)
                flash("Đã lưu khai báo. Nháp cũ cần được tạo lại.","success")
            except (ValueError,KeyError) as exc:
                flash(str(exc)[:1000],"error")
            return redirect(url_for("setup_data"))
        with store.lock:
            data=store.data()
        return render_template("setup.html",data=data,classes=sorted({s["class_id"] for s in data["Sessions"]}))
