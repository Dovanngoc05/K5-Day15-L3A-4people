"""Validate inputs and build the integer CP-SAT scheduling model."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ortools.sat.python import cp_model

from .schedule_excel import day_value, minutes, rows, split


@dataclass(frozen=True)
class Slot:
    key: str
    day: date
    start: int
    end: int
    rooms: tuple
    capacity: int

    @property
    def duration(self):
        return self.end - self.start


def integer(text, label, minimum=0, maximum=100000):
    if not text.isascii() or not text.isdecimal() or len(text) > 6:
        raise ValueError(f"{label} phải là số nguyên.")
    value = int(text)
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} phải từ {minimum} đến {maximum}.")
    return value


def flag(text, label):
    if text.casefold() in {"0", "false"}:
        return False
    if text.casefold() in {"1", "true"}:
        return True
    raise ValueError(f"{label} phải là 0 hoặc 1.")


def indexed(book, sheet, column):
    result = {}
    for number, row in rows(book, sheet):
        key = row[column]
        if not key or key in result:
            raise ValueError(f"{sheet}, dòng {number}. {column} trống hoặc trùng.")
        result[key] = row
    return result


def availability(book, sheet, people):
    result = defaultdict(list)
    for index, row in rows(book, sheet):
        person = row["person"]
        start, end = minutes(row["start"]), minutes(row["end"])
        if person not in people or start >= end:
            raise ValueError(f"{sheet}, dòng {index}. Người hoặc khoảng giờ không hợp lệ.")
        result[person, day_value(row["day"])].append((start, end, flag(row["preferred"], sheet)))
    return result


def solve(books, previous=None):
    teaching, coaching, learners = books
    classes = indexed(teaching, "Classes", "class_id")
    students = indexed(learners, "Learners", "student_id")
    teachers = indexed(teaching, "Teachers", "person")
    coaches = indexed(coaching, "Coaches", "person")
    if not classes or not students:
        raise ValueError("Cần ít nhất một lớp và một học viên.")
    if len(classes) > 250 or len(students) > 5000 or len(teachers) + len(coaches) > 350:
        raise ValueError("Dữ liệu vượt giới hạn 250 lớp, 5.000 học viên hoặc 350 nhân sự.")
    for person, coach in coaches.items():
        roles = set(split(coach["role"]))
        if not roles or not roles <= {"lab", "key"}:
            raise ValueError(f"Coaches · {person} cần role lab, key hoặc lab;key.")
    staff = {}
    for pool in (teachers, coaches):
        for person, row in pool.items():
            limits = (integer(row["daily_minutes"], f"{person} daily_minutes", 1, 1440),
                      integer(row["weekly_minutes"], f"{person} weekly_minutes", 1, 10080))
            if not split(row["skills"]) or (person in staff and limits != staff[person]):
                raise ValueError(f"{person} cần skills và giới hạn giờ nhất quán.")
            staff[person] = limits
    group_members = defaultdict(list)
    for ident, row in students.items():
        group = row["group"]
        if not group or ";" in group or not row["full_name"]:
            raise ValueError(f"Learners · {ident} cần full_name và đúng một group.")
        group_members[group].append(ident)
    teacher_hours = availability(teaching, "TeacherAvailability", teachers)
    coach_hours = availability(coaching, "CoachAvailability", coaches)
    group_keys = {f"group:{group}": group for group in group_members}
    if students.keys() & group_keys.keys():
        raise ValueError("Mã học viên trùng ký hiệu group:<nhóm> trong LearnerAvailability.")
    learner_hours = availability(learners, "LearnerAvailability", students.keys() | group_keys.keys())
    for (person, day), windows in list(learner_hours.items()):
        if person in group_keys:
            for sid in group_members[group_keys[person]]:
                learner_hours.setdefault((sid, day), windows)
            del learner_hours[person, day]
    slots = defaultdict(list)
    for key, row in indexed(teaching, "Slots", "slot_id").items():
        cid = row["class_id"]
        start, end = minutes(row["start"]), minutes(row["end"])
        rooms = split(row["rooms"])
        if cid not in classes or not rooms or start >= end:
            raise ValueError(f"Slots · {key} cần lớp có thật, phòng và khoảng giờ hợp lệ.")
        slots[cid].append(Slot(key, day_value(row["day"]), start, end, rooms,
                               integer(row["capacity"], f"{key} capacity", 1)))
    if sum(map(len, slots.values())) > 1500:
        raise ValueError("Chỉ hỗ trợ tối đa 1.500 phương án khung giờ/phòng.")
    previous = previous or {}
    for cid, old in previous.items():
        if old["locked"] and (cid not in classes or not flag(classes[cid]["locked"], cid)):
            raise ValueError(f"HC-10 · Lớp đang khóa {cid} phải được giữ lại với locked=1.")

    model = cp_model.CpModel()
    intervals = defaultdict(list)
    activities = defaultdict(list)
    options = defaultdict(list)
    penalties = []

    def add_activity(resource, slot, selected):
        absolute = slot.day.toordinal() * 1440 + slot.start
        intervals[resource].append(model.new_optional_fixed_size_interval_var(
            absolute, slot.duration, selected, f"interval_{len(intervals[resource])}"))
        if resource[0] != "room":
            activities[resource, slot.day].append((slot, selected))

    def available(calendar, person, slot):
        return any(start <= slot.start and slot.end <= end
                   for start, end, _ in calendar[person, slot.day])

    def penalty(calendar, person, slot, weight):
        preferences = calendar_preferences.get((person, id(calendar)), ())
        return weight if preferences and not any(
            day == slot.day and start <= slot.start and slot.end <= end
            for day, start, end in preferences) else 0

    calendar_preferences = defaultdict(list)
    for calendar in (learner_hours, teacher_hours, coach_hours):
        for (person, day), windows in calendar.items():
            calendar_preferences[person, id(calendar)].extend(
                (day, start, end) for start, end, preferred in windows if preferred)

    class_meta = {}
    for cid, row in classes.items():
        groups = split(row["groups"])
        if not groups or any(group not in group_members for group in groups) or not row["subject"]:
            raise ValueError(f"Classes · {cid} cần chuyên đề và nhóm có trong Learners.")
        members = tuple(sorted(ident for group in groups for ident in group_members[group]))
        lab_count = integer(row["assistants"], f"{cid} assistants", maximum=15)
        key_count = integer(row["keys"], f"{cid} keys", maximum=15)
        locked = flag(row["locked"], cid)
        old = previous.get(cid)
        existing_slot = old["slot"] if old else row["existing_slot"]
        existing_teacher = old["teacher"] if old else row["existing_teacher"]
        existing_coaches = old["coaches"] if old else split(row["existing_coaches"])
        if locked and (not existing_slot or not existing_teacher or len(existing_coaches) != lab_count + key_count):
            raise ValueError(f"HC-10 · {cid} cần phương án hiện tại đầy đủ trước khi khóa.")
        if old and old["locked"] and (old["subject"] != row["subject"] or old["students"] != members
                                      or old["lab_count"] != lab_count or old["key_count"] != key_count):
            raise ValueError(f"HC-10 · Dữ liệu lớp đã khóa {cid} bị thay đổi.")
        class_meta[cid] = dict(subject=row["subject"], students=members, locked=locked,
                               lab_count=lab_count, key_count=key_count, groups=groups)
        kept = []
        for slot in slots[cid]:
            if slot.capacity < len(members) or not all(available(learner_hours, person, slot)
                                                       for person in members):
                continue
            same_slot = slot.key == existing_slot and (not old or (
                old["day"], old["start"], old["end"], old["rooms"]) ==
                (slot.day.isoformat(), slot.start, slot.end, slot.rooms))
            if locked and not same_slot:
                continue
            teacher_pool = [person for person, data in teachers.items()
                            if row["subject"] in split(data["skills"]) and available(teacher_hours, person, slot)
                            and (not locked or person == existing_teacher)]
            lab_pool, key_pool = [], []
            for person, data in coaches.items():
                if row["subject"] not in split(data["skills"]) or not available(coach_hours, person, slot):
                    continue
                if locked and person not in existing_coaches:
                    continue
                roles = split(data["role"])
                if lab_count and "lab" in roles:
                    lab_pool.append(person)
                if key_count and "key" in roles:
                    key_pool.append(person)
            if (not teacher_pool or len(lab_pool) < lab_count or len(key_pool) < key_count
                    or len(set(lab_pool + key_pool)) < lab_count + key_count):
                continue
            selected = model.new_bool_var(f"slot_{slot.key}")
            options[cid].append((slot, selected, {}))
            assignments = options[cid][-1][2]
            for role, pool, count, calendar, weight in (
                ("teacher", teacher_pool, 1, teacher_hours, 20),
                ("lab", lab_pool, lab_count, coach_hours, 5),
                ("key", key_pool, key_count, coach_hours, 5),
            ):
                choices = assignments[role] = {}
                for person in pool:
                    chosen = choices[person] = model.new_bool_var(f"{slot.key}_{role}_{person}")
                    add_activity(("staff", person), slot, chosen)
                    penalties.append(penalty(calendar, person, slot, weight) * chosen)
                model.add(sum(choices.values()) == count * selected)
            for room in slot.rooms:
                add_activity(("room", room), slot, selected)
            for group in groups:
                add_activity(("group", group), slot, selected)
            penalties.append(sum(penalty(learner_hours, person, slot, 30)
                                 for person in members) * selected)
            if same_slot:
                checks = [selected]
                if existing_teacher:
                    checks.append(assignments["teacher"].get(existing_teacher, 0))
                checks.extend(assignments["lab"].get(person, 0) + assignments["key"].get(person, 0)
                              for person in existing_coaches)
                if old:
                    checks.extend(assignments[role].get(person, 0)
                                  for role in ("lab", "key") for person in old[role])
                flag_kept = model.new_bool_var(f"kept_{slot.key}")
                model.add(sum(checks) == len(checks)).only_enforce_if(flag_kept)
                kept.append(flag_kept)
                if locked and old:
                    model.add(flag_kept == 1)
        if not options[cid]:
            raise ValueError(f"{cid} · Không có phương án đáp ứng sức chứa, thời gian rảnh, "
                             "năng lực, nhân sự tối thiểu và lịch khóa (HC-04–07, HC-09–10).")
        model.add_exactly_one(selected for _, selected, _ in options[cid])
        if existing_slot:
            penalties.append(100 * (1 - sum(kept)))

    for resource_intervals in intervals.values():
        model.add_no_overlap(resource_intervals)
    weekly = defaultdict(list)
    total = defaultdict(list)
    for (resource, day), entries in activities.items():
        duration = sum(slot.duration * chosen for slot, chosen in entries)
        kind, person = resource
        if kind == "staff":
            model.add(duration <= staff[person][0])
            weekly[person, day.isocalendar()[:2]].append(duration)
            total[person].append(duration)
        if len(entries) < 2:
            continue
        first = model.new_int_var(0, 1440, "first_start")
        last = model.new_int_var(0, 1440, "last_end")
        model.add_min_equality(first, [1440 + (slot.start - 1440) * chosen for slot, chosen in entries])
        model.add_max_equality(last, [slot.end * chosen for slot, chosen in entries])
        gap = model.new_int_var(0, 1440, "gap")
        model.add_max_equality(gap, [last - first - duration, 0])
        blocks = model.new_int_var(0, 24, "gap_hours")
        model.add_division_equality(blocks, gap + 59, 60)
        penalties.append(10 * blocks)
    for (person, _), durations in weekly.items():
        model.add(sum(durations) <= staff[person][1])
    horizon = len(classes) * 24
    for pool, weight in ((teachers, 20), (coaches, 15)):
        if len(pool) < 2:
            continue
        counts = [sum(total[person]) for person in pool]
        high = model.new_int_var(0, horizon * 60, "max_work")
        low = model.new_int_var(0, horizon * 60, "min_work")
        model.add_max_equality(high, counts)
        model.add_min_equality(low, counts)
        spread = model.new_int_var(0, horizon, "workload_spread_hours")
        difference = model.new_int_var(0, horizon * 60, "workload_difference")
        model.add(difference == high - low)
        model.add_division_equality(spread, difference + 59, 60)
        penalties.append(weight * spread)

    model.minimize(sum(penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20
    solver.parameters.num_workers = 4
    status = solver.solve(model)
    if status == cp_model.MODEL_INVALID:
        raise RuntimeError(model.validate())
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        description = ("Không thể xếp lịch đồng thời. Kiểm tra ca trùng, giới hạn giờ và lịch khóa."
                       if status == cp_model.INFEASIBLE else "Chưa tìm được lịch trong thời gian cho phép.")
        raise ValueError(f"{solver.status_name(status)} · {description}")
    result = {}
    for cid, entries in options.items():
        slot, _, roles = next(entry for entry in entries if solver.value(entry[1]))
        assignment = {role: tuple(person for person, var in choices.items() if solver.value(var))
                      for role, choices in roles.items()}
        result[cid] = dict(class_meta[cid], slot=slot.key, day=slot.day.isoformat(),
                           start=slot.start, end=slot.end, rooms=slot.rooms,
                           teacher=assignment["teacher"][0], lab=assignment["lab"], key=assignment["key"],
                           coaches=assignment["lab"] + assignment["key"])
    return students, result, solver.status_name(status), round(solver.objective_value)
