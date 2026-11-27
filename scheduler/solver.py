"""CP-SAT scheduling with integer minutes, HC-01..11 and configurable SC-01..07."""
from collections import defaultdict
from datetime import date, datetime
from itertools import combinations

from ortools.sat.python import cp_model

from .excel import DEFAULT_WEIGHTS, split, text

ROLES = {"teacher", "assistant", "key_coach", "student"}


def integer(value, label, minimum=0, maximum=100_000):
    raw=text(value)
    if not raw:
        raise ValueError(label + ": chưa điền; cần số nguyên từ %d đến %d" % (minimum,maximum))
    try:
        number = int(raw)
    except (ValueError,TypeError) as exc:
        raise ValueError(label + ": cần số nguyên từ %d đến %d" % (minimum,maximum)) from exc
    if str(number) != text(value) or not minimum <= number <= maximum:
        raise ValueError(label + ": cần số nguyên trong khoảng cho phép")
    return number


def slot_time(slot):
    day = date.fromisoformat(text(slot["date"]))
    start = datetime.strptime(text(slot["start"]), "%H:%M").time()
    end = datetime.strptime(text(slot["end"]), "%H:%M").time()
    a, b = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    if a >= b:
        raise ValueError("Khung giờ phải kết thúc sau bắt đầu trong cùng ngày")
    return day, a, b


def readiness(data):
    errors = []
    def problem(code, message):
        errors.append({"code": code, "message": message})
    maps = {}
    for table, key in [("People", "person_id"), ("Sessions", "session_id"), ("Slots", "slot_id"), ("Rooms", "room_id")]:
        rows = data.get(table, [])
        if not rows:
            problem("DATA", "Thiếu bảng hoặc dữ liệu: " + table)
        maps[table] = {}
        for row in rows:
            ident = text(row.get(key))
            if not ident or ident in maps[table]:
                problem("DATA", table + ": mã trống hoặc trùng " + ident)
            maps[table][ident] = row
            if len(ident)>160 or any(ord(c)<32 for c in ident) or "|" in ident or ident.startswith("room:"):
                problem("DATA", table + ": mã quá dài/chứa ký tự điều khiển hoặc tiền tố dành riêng")
    people, sessions, slots, rooms = (maps[k] for k in ["People", "Sessions", "Slots", "Rooms"])
    if len(sessions) > 200 or len(slots) > 100 or len(people) > 2000:
        problem("LIMIT", "Bản local hỗ trợ tối đa 200 buổi, 100 khung giờ, 2.000 người mỗi lần xếp.")
    parsed = {}
    for sid, slot in slots.items():
        try:
            parsed[sid] = slot_time(slot)
        except (ValueError, KeyError) as exc:
            problem("DATA", "Slots/" + sid + ": " + str(exc))
    for pid, person in people.items():
        if person.get("role") not in ROLES:
            problem("DATA", "Vai trò không hợp lệ: " + pid)
        if person.get("role") != "student":
            for field in ["max_minutes_day", "max_minutes_week"]:
                try:
                    integer(person.get(field), field, 1, 10080)
                except (ValueError, TypeError):
                    problem("HC-08", pid + " thiếu/sai " + field)
    enroll = defaultdict(set)
    for row in data.get("Enrollments", []):
        pid, cls = text(row.get("person_id")), text(row.get("class_id"))
        if pid not in people or people[pid].get("role") != "student" or not cls:
            problem("HC-02", "Đăng ký lớp không hợp lệ: " + pid + "/" + cls)
        else:
            enroll[cls].add(pid)
    availability = {}
    for row in data.get("Availability", []):
        key = (text(row.get("person_id")), text(row.get("slot_id")))
        if key in availability or key[0] not in people or key[1] not in slots:
            problem("HC-04", "Giờ rảnh trùng hoặc không nối được mã: " + str(key))
        if text(row.get("available")) not in {"0", "1"} or text(row.get("preferred")) not in {"0", "1"}:
            problem("HC-04", "available/preferred phải là 0 hoặc 1: " + str(key))
        availability[key] = row
    used_people = {pid for ids in enroll.values() for pid in ids}
    used_people.update(pid for pid, p in people.items() if p.get("role") != "student")
    missing = [(p, s) for p in sorted(used_people) for s in slots if (p, s) not in availability]
    if missing:
        problem("HC-04", "Thiếu %d dòng giờ rảnh; ví dụ %s. Cần khai báo rõ available=0/1." % (len(missing), missing[:3]))
    for rid, room in rooms.items():
        try:
            integer(room.get("capacity"), "capacity", 1)
        except (ValueError, TypeError):
            problem("HC-07", "Thiếu/sai sức chứa phòng: " + rid)
    for sid, session in sessions.items():
        if not enroll[text(session.get("class_id"))]:
            problem("HC-02", sid + ": thiếu học viên đăng ký lớp " + text(session.get("class_id")))
        for field,minimum,maximum in [("duration_minutes",1,1440),("assistant_count",0,10),("key_coach_required",0,1),("locked",0,1)]:
            try:
                integer(session.get(field), field, minimum, maximum)
            except (ValueError, TypeError) as exc:
                problem("DATA", sid + ": " + str(exc))
        if not split(session.get("allowed_slots")) <= slots.keys():
            problem("DATA",sid+": allowed_slots chứa mã khung giờ không tồn tại")
        if not split(session.get("allowed_rooms")) <= rooms.keys():
            problem("DATA",sid+": allowed_rooms chứa mã phòng không tồn tại")
        if not text(session.get("subject")):
            problem("HC-05", sid + ": thiếu môn/chủ đề để đối chiếu chuyên môn")
        if (text(session.get("assistant_count")) not in {"", "0"} or text(session.get("key_coach_required"))=="1") and not text(session.get("required_skill")):
            problem("HC-06", sid + ": cần khai báo kỹ năng coach")
        if text(session.get("locked")) == "1":
            required = ["baseline_slot", "baseline_teacher", "baseline_room"]
            if text(session.get("assistant_count")) != "0":
                required.append("baseline_assistants")
            if text(session.get("key_coach_required")) == "1":
                required.append("baseline_key_coach")
            if any(not text(session.get(f)) for f in required):
                problem("HC-10", sid + ": lịch khoá thiếu baseline đầy đủ")
            if text(session.get("baseline_slot")) not in slots or text(session.get("baseline_teacher")) not in people or text(session.get("baseline_room")) not in rooms:
                problem("HC-10", sid + ": baseline không liên kết được khung giờ/người/phòng")
            try:
                if len(split(session.get("baseline_assistants")))!=int(session.get("assistant_count",0)):
                    problem("HC-10", sid + ": baseline phải chỉ rõ đúng số coach")
            except ValueError:
                pass
    weight_ids = set()
    for row in data.get("Weights", []):
        key = row.get("constraint_id")
        try:
            if key not in DEFAULT_WEIGHTS or key in weight_ids:
                raise ValueError("Mã SC trùng/không hợp lệ")
            integer(row.get("weight"), "weight", 0, 10000)
            weight_ids.add(key)
        except (ValueError, TypeError) as exc:
            problem("SC", str(exc))
    if weight_ids != set(DEFAULT_WEIGHTS):
        problem("SC", "Cần đủ trọng số SC-01 đến SC-07 (có thể đặt 0)")
    return errors


def _people_for(row, enrollments):
    return set(enrollments.get(row["class_id"], set())) | {row["teacher_id"]} | split(row.get("assistant_ids")) | split(row.get("key_coach_id"))


def validate_solution(data, schedule):
    """Independently recheck every hard constraint before publishing."""
    errors = readiness(data)
    if errors:
        return errors
    people = {p["person_id"]: p for p in data["People"]}
    sessions = {s["session_id"]: s for s in data["Sessions"]}
    slots = {s["slot_id"]: s for s in data["Slots"]}
    rooms = {r["room_id"]: r for r in data["Rooms"]}
    av = {(r["person_id"], r["slot_id"]): r for r in data["Availability"]}
    enroll = defaultdict(set)
    for r in data["Enrollments"]:
        enroll[r["class_id"]].add(r["person_id"])
    if len(schedule) != len(sessions) or {r.get("session_id") for r in schedule} != set(sessions):
        return [{"code": "HC-09", "message": "Lịch phải chứa đúng mỗi buổi một lần"}]
    intervals = []
    loads = defaultdict(int)
    for row in schedule:
        sid = row["session_id"]
        source = sessions[sid]
        slot_id = row.get("slot_id")
        tid, rid = row.get("teacher_id"), row.get("room_id")
        assistants, keys = split(row.get("assistant_ids")), split(row.get("key_coach_id"))
        if slot_id not in slots or tid not in people or rid not in rooms or not (assistants | keys) <= people.keys():
            errors.append({"code": "DATA", "message": sid + ": mã không hợp lệ"})
            continue
        day, start, slot_end = slot_time(slots[slot_id])
        duration = int(source["duration_minutes"])
        end = start + duration
        def fail(code, message):
            errors.append({"code": code, "message": sid + ": " + message})
        if row.get("class_id") != source["class_id"] or end > slot_end:
            fail("DATA", "sai lớp hoặc vượt khung giờ")
        if split(source.get("allowed_slots")) and slot_id not in split(source.get("allowed_slots")):
            fail("DATA", "khung giờ ngoài allowed_slots")
        if split(source.get("allowed_rooms")) and rid not in split(source.get("allowed_rooms")):
            fail("DATA", "phòng ngoài allowed_rooms")
        if any(text(row.get(k))!=v for k,v in {"date":day.isoformat(),"start":f"{start//60:02}:{start%60:02}","end":f"{end//60:02}:{end%60:02}","subject":source["subject"]}.items()):
            fail("DATA", "nội dung hiển thị không khớp khung giờ/chủ đề gốc")
        if people[tid]["role"] != "teacher" or source["subject"] not in split(people[tid].get("subjects")):
            fail("HC-05", "giảng viên không đúng chuyên môn")
        if len(assistants) != int(source["assistant_count"]) or len(keys) != int(source["key_coach_required"]):
            fail("HC-06", "thiếu/sai số coach")
        if assistants & keys:
            fail("HC-03", "một người không nhận đồng thời hai vai")
        for pid in assistants | keys:
            role = "key_coach" if pid in keys else "assistant"
            if people[pid]["role"] != role or not split(source["required_skill"]) <= split(people[pid].get("skills")):
                fail("HC-06", "coach sai vai hoặc thiếu kỹ năng: " + pid)
        learner_ids = enroll[source["class_id"]]
        if len(learner_ids) > int(rooms[rid]["capacity"]):
            fail("HC-07", "phòng không đủ sức chứa")
        all_ids = learner_ids | {tid} | assistants | keys
        for pid in all_ids:
            if av[(pid, slot_id)]["available"] not in (1, "1"):
                fail("HC-04", "người không rảnh: " + pid)
            if people[pid]["role"] != "student":
                loads[(pid, "day", day.isoformat())] += duration
                iso = day.isocalendar()
                loads[(pid, "week", (iso.year, iso.week))] += duration
        if text(source.get("locked")) == "1":
            for key, value in [("baseline_slot", slot_id), ("baseline_teacher", tid), ("baseline_room", rid), ("baseline_key_coach", row.get("key_coach_id", ""))]:
                if text(source.get(key)) != text(value):
                    fail("HC-10", "thay đổi lịch khoá: " + key)
            if split(source.get("baseline_assistants")) != assistants:
                fail("HC-10", "thay coach lịch khoá")
        intervals.append((sid, day, start, end, all_ids, rid))
    for a, b in combinations(intervals, 2):
        if a[1] == b[1] and a[2] < b[3] and b[2] < a[3]:
            if a[5] == b[5]:
                errors.append({"code": "HC-11", "message": f"{a[0]} và {b[0]} trùng phòng {a[5]}"})
            for pid in a[4] & b[4]:
                role = people[pid]["role"]
                code = "HC-01" if role == "teacher" else "HC-02" if role == "student" else "HC-03"
                errors.append({"code": code, "message": f"{pid}: {a[0]} và {b[0]} chồng giờ"})
    for (pid, period, _), minutes in loads.items():
        if minutes > int(people[pid]["max_minutes_" + period]):
            errors.append({"code": "HC-08", "message": pid + ": vượt giờ làm " + period})
    return errors


def baseline_schedule(data):
    """Use a baseline as a hint only if the independent checker accepts it."""
    slots={s["slot_id"]:s for s in data["Slots"]}
    rows=[]
    try:
        for s in data["Sessions"]:
            slot=text(s.get("baseline_slot"))
            day,start,stop=slot_time(slots[slot])
            end=start+int(s["duration_minutes"])
            rows.append(dict(session_id=s["session_id"],class_id=s["class_id"],subject=s["subject"],slot_id=slot,
                date=day.isoformat(),start=f"{start//60:02}:{start%60:02}",end=f"{end//60:02}:{end%60:02}",
                teacher_id=text(s.get("baseline_teacher")),assistant_ids=text(s.get("baseline_assistants")),
                key_coach_id=text(s.get("baseline_key_coach")),room_id=text(s.get("baseline_room")),locked=text(s.get("locked"))))
    except (KeyError,ValueError):
        return []
    return [] if validate_solution(data,rows) else rows


def solve(data, seconds=15):
    errors = readiness(data)
    if errors:
        return {"status": "MISSING_DATA", "errors": errors, "schedule": []}
    model = cp_model.CpModel()
    people = {p["person_id"]: p for p in data["People"]}
    slots = {s["slot_id"]: s for s in data["Slots"]}
    times = {sid: slot_time(s) for sid, s in slots.items()}
    rooms = {r["room_id"]: r for r in data["Rooms"]}
    av = {(r["person_id"], r["slot_id"]): r for r in data["Availability"]}
    enroll = defaultdict(set)
    for r in data["Enrollments"]:
        enroll[r["class_id"]].add(r["person_id"])
    # Exact aggregation: identical enrolments and availability/preferences have
    # identical student constraints. Keep individual IDs for final validation.
    classes_by_person=defaultdict(set)
    for cls,members in enroll.items():
        for pid in members:
            classes_by_person[pid].add(cls)
    groups=defaultdict(list)
    for pid,classes in classes_by_person.items():
        signature=(tuple(sorted(classes)),tuple((text(av[(pid,slot)]["available"]),text(av[(pid,slot)]["preferred"])) for slot in slots))
        groups[signature].append(pid)
    representative={}
    multiplicity={}
    for members in groups.values():
        first=min(members)
        multiplicity[first]=len(members)
        for pid in members:
            representative[pid]=first
    weights = {r["constraint_id"]: int(r["weight"]) for r in data["Weights"]}
    resources = defaultdict(list)
    duties = defaultdict(list)
    penalties = defaultdict(list)
    choices = {}
    session_slots = {}
    teachers, assistants, keys, room_vars = {}, {}, {}, {}
    origin = min(day for day, _, _ in times.values())
    count = 0

    def available(pid, slot):
        return text(av[(pid, slot)]["available"]) == "1"

    def duty(pid, sid, slot, duration, selected):
        nonlocal count
        count += 1
        if count > 100_000:
            raise ValueError("Quá nhiều tổ hợp. Hãy giảm phạm vi lịch hoặc khung giờ.")
        day, start, _ = times[slot]
        absolute = (day - origin).days * 1440 + start
        interval = model.new_optional_fixed_size_interval_var(absolute, duration, selected, f"duty_{count}")
        resources[pid].append(interval)
        duties[pid].append((day, start, duration, selected))
        role = people[pid]["role"]
        code = "SC-02" if role == "student" else "SC-03" if role == "teacher" else "SC-07"
        if text(av[(pid, slot)]["preferred"]) == "0":
            penalties[code].append(60 * multiplicity.get(pid,1) * selected)

    for session in data["Sessions"]:
        sid = session["session_id"]
        duration = int(session["duration_minutes"])
        learner_ids = enroll[session["class_id"]]
        xs = []
        for slot, (day, start, end) in times.items():
            if split(session.get("allowed_slots")) and slot not in split(session.get("allowed_slots")):
                continue
            if duration > end-start or any(not available(p, slot) for p in learner_ids):
                continue
            if text(session.get("locked")) == "1" and slot != session["baseline_slot"]:
                continue
            x = model.new_bool_var(f"slot_{sid}_{slot}")
            session_slots[(sid, slot)] = x
            xs.append(x)
            for pid in {representative[p] for p in learner_ids}:
                duty(pid, sid, slot, duration, x)
            for role, destination, required in [("teacher", teachers, 1), ("assistant", assistants, int(session["assistant_count"])), ("key_coach", keys, int(session["key_coach_required"]))]:
                vs = []
                for pid, person in people.items():
                    if person["role"] != role or not available(pid, slot):
                        continue
                    if role == "teacher" and session["subject"] not in split(person.get("subjects")):
                        continue
                    if role != "teacher" and not split(session["required_skill"]) <= split(person.get("skills")):
                        continue
                    if text(session.get("locked")) == "1":
                        baseline = split(session.get({"teacher": "baseline_teacher", "assistant": "baseline_assistants", "key_coach": "baseline_key_coach"}[role]))
                        if pid not in baseline:
                            continue
                    v = model.new_bool_var(f"{role}_{sid}_{slot}_{pid}")
                    destination[(sid, slot, pid)] = v
                    vs.append(v)
                    duty(pid, sid, slot, duration, v)
                model.add(sum(vs) == required * x)
            rs = []
            for rid, room in rooms.items():
                if split(session.get("allowed_rooms")) and rid not in split(session.get("allowed_rooms")):
                    continue
                if int(room["capacity"]) < len(learner_ids):
                    continue
                if text(session.get("locked")) == "1" and rid != session["baseline_room"]:
                    continue
                v = model.new_bool_var(f"room_{sid}_{slot}_{rid}")
                room_vars[(sid, slot, rid)] = v
                rs.append(v)
                absolute = (day-origin).days * 1440 + start
                resources["room:" + rid].append(model.new_optional_fixed_size_interval_var(absolute, duration, v, f"roomint_{sid}_{slot}_{rid}"))
            model.add(sum(rs) == x)
        if not xs:
            return {"status": "INFEASIBLE", "errors": [{"code": "HC", "message": sid + ": không có khung giờ phù hợp học viên/lịch khoá/thời lượng"}], "schedule": []}
        model.add_exactly_one(xs)
        choices[sid] = xs
        if text(session.get("baseline_slot")):
            conditions = [session_slots.get((sid, session["baseline_slot"]), 0)]
            for collection, field in [(teachers, "baseline_teacher"), (room_vars, "baseline_room"), (keys, "baseline_key_coach")]:
                pid = text(session.get(field))
                if pid:
                    conditions.append(collection.get((sid, session["baseline_slot"], pid), 0))
            baseline_as = split(session.get("baseline_assistants"))
            for (ss, slot, pid), v in assistants.items():
                if ss == sid:
                    conditions.append(v if slot == session["baseline_slot"] and pid in baseline_as else 1-v)
            changed = model.new_bool_var("changed_" + sid)
            for c in conditions:
                model.add(changed >= 1-c)
            model.add(changed <= sum(1-c for c in conditions))
            penalties["SC-01"].append(60 * changed)
    for intervals in resources.values():
        model.add_no_overlap(intervals)
    totals = defaultdict(list)
    bound = sum(int(s["duration_minutes"]) for s in data["Sessions"])
    for pid, items in duties.items():
        person = people[pid]
        by_day, by_week = defaultdict(list), defaultdict(list)
        for day, start, duration, selected in items:
            by_day[day].append((start, duration, selected))
            iso = day.isocalendar()
            by_week[(iso.year, iso.week)].append(duration * selected)
        if person["role"] != "student":
            for rows in by_day.values():
                model.add(sum(duration*v for _, duration, v in rows) <= int(person["max_minutes_day"]))
            for rows in by_week.values():
                model.add(sum(rows) <= int(person["max_minutes_week"]))
        for day, rows in by_day.items():
            starts, ends = [], []
            for i, (start, duration, v) in enumerate(rows):
                first = model.new_int_var(0, 1440, f"first_{pid}_{day}_{i}")
                last = model.new_int_var(0, 1440, f"last_{pid}_{day}_{i}")
                model.add(first == start).only_enforce_if(v)
                model.add(first == 1440).only_enforce_if(v.Not())
                model.add(last == start+duration).only_enforce_if(v)
                model.add(last == 0).only_enforce_if(v.Not())
                starts.append(first)
                ends.append(last)
            first = model.new_int_var(0,1440,f"firstday_{pid}_{day}")
            last = model.new_int_var(0,1440,f"lastday_{pid}_{day}")
            gap = model.new_int_var(0,1440,f"gap_{pid}_{day}")
            model.add_min_equality(first, starts)
            model.add_max_equality(last, ends)
            model.add_max_equality(gap, [0, last-first-sum(duration*v for _, duration,v in rows)])
            penalties["SC-06"].append(multiplicity.get(pid,1)*gap)
        load = model.new_int_var(0,bound,"load_"+pid)
        model.add(load == sum(duration*v for _,_,duration,v in items))
        totals[person["role"]].append(load)
    for role, code in [("teacher","SC-04"),("assistant","SC-05")]:
        for pid, person in people.items():
            if person["role"] == role and pid not in duties:
                totals[role].append(0)
        if totals[role]:
            high=model.new_int_var(0,bound,"max_"+role)
            low=model.new_int_var(0,bound,"min_"+role)
            model.add_max_equality(high,totals[role])
            model.add_min_equality(low,totals[role])
            penalties[code].append(high-low)
    model.minimize(sum(weights[code]*sum(values) for code,values in penalties.items()))
    initial={r["session_id"]:r for r in baseline_schedule(data)}
    if initial:
        for (sid,slot),v in session_slots.items():
            model.add_hint(v,int(initial[sid]["slot_id"]==slot))
        for collection,field in [(teachers,"teacher_id"),(assistants,"assistant_ids"),(keys,"key_coach_id"),(room_vars,"room_id")]:
            for (sid,slot,pid),v in collection.items():
                model.add_hint(v,int(initial[sid]["slot_id"]==slot and pid in split(initial[sid][field])))
    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=max(1,min(30,float(seconds)))
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=42
    status=solver.solve(model)
    elapsed=solver.wall_time
    fallback=False
    if status==cp_model.UNKNOWN and initial:
        # Obtain a CP-SAT-verified feasible baseline when optimization times out.
        # Its OPTIMAL status applies to the fixed submodel, not the original.
        solver=cp_model.CpSolver()
        solver.parameters.max_time_in_seconds=5
        solver.parameters.num_search_workers=1
        solver.parameters.fix_variables_to_their_hinted_value=True
        status=solver.solve(model)
        elapsed+=solver.wall_time
        fallback=status in (cp_model.OPTIMAL,cp_model.FEASIBLE)
    name=solver.status_name(status)
    if fallback:
        name="FEASIBLE"
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return {"status":name,"schedule":[],"errors":[{"code":"SOLVER","message":"Không tìm được lịch hợp lệ. Kiểm tra giờ rảnh, chuyên môn, phòng, giới hạn giờ và lịch khoá. UNKNOWN nghĩa là chưa kết luận được trong thời gian cho phép."}]}
    schedule=[]
    for s in data["Sessions"]:
        sid=s["session_id"]
        slot=next(slot for (ss,slot),v in session_slots.items() if ss==sid and solver.value(v))
        def picked(collection):
            return sorted(pid for (ss,sl,pid),v in collection.items() if ss==sid and sl==slot and solver.value(v))
        day,start,_=times[slot]
        end=start+int(s["duration_minutes"])
        schedule.append(dict(session_id=sid,class_id=s["class_id"],subject=s["subject"],slot_id=slot,date=day.isoformat(),
            start=f"{start//60:02}:{start%60:02}",end=f"{end//60:02}:{end%60:02}",teacher_id=picked(teachers)[0],
            assistant_ids="|".join(picked(assistants)),key_coach_id="|".join(picked(keys)),room_id=picked(room_vars)[0],locked=text(s.get("locked"))))
    errors=validate_solution(data,schedule)
    return {"status":"INVALID" if errors else name,"schedule":schedule if not errors else [],"errors":errors,
        "score":solver.objective_value/60,"penalties":[dict(constraint_id=code,weight=weights[code],units=solver.value(sum(penalties[code]))/60,
        penalty=weights[code]*solver.value(sum(penalties[code]))/60) for code in DEFAULT_WEIGHTS],"seconds":round(elapsed,3),
        "method":"CP-SAT verified baseline after optimization timeout; optimality not proven" if fallback else "CP-SAT optimization"}
