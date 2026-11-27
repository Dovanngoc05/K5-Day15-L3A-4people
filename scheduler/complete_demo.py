"""Create an explicitly synthetic, complete scenario without changing locked source data."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from datetime import date
from collections import defaultdict,deque

from .excel import SCHEMA, atomic_write, read_tables, text
from .solver import readiness,slot_time,validate_solution

SCENARIO_INFO = dict(kind="synthetic",label="KỊCH BẢN DEMO GIẢ LẬP — KHÔNG PHẢI LỊCH ĐÃ XÁC NHẬN",
    note="Đăng ký lớp, giờ rảnh, sức chứa và chuyên môn được bổ sung giả lập. Kho dữ liệu và các lịch khoá gốc được giữ nguyên. Admin duyệt trước khi hiển thị lịch cá nhân.")


def seed_schedule(data):
    """Construct a feasible synthetic starting point; it is never auto-published."""
    enroll=defaultdict(set)
    for row in data["Enrollments"]:
        enroll[row["class_id"]].add(row["person_id"])
    av={(r["person_id"],r["slot_id"]):int(r["available"]) for r in data["Availability"]}
    slots={s["slot_id"]:s for s in data["Slots"]}
    by_day=defaultdict(list)
    for s in data["Sessions"]:
        first=s["allowed_slots"].split("|")[0]
        by_day[slots[first]["date"]].append(s)
    loads=defaultdict(int)
    result=[]
    for day,rows in sorted(by_day.items()):
        colors={}
        graph={s["session_id"]:set() for s in rows}
        for i,a in enumerate(rows):
            for b in rows[i+1:]:
                if enroll[a["class_id"]]&enroll[b["class_id"]]:
                    graph[a["session_id"]].add(b["session_id"])
                    graph[b["session_id"]].add(a["session_id"])
        for sid in sorted(graph):
            if sid in colors:
                continue
            colors[sid]=0
            queue=deque([sid])
            while queue:
                current=queue.popleft()
                for neighbor in graph[current]:
                    if neighbor in colors:
                        if colors[neighbor]==colors[current]:
                            raise ValueError("Kịch bản cần hơn hai ca trong ngày "+day)
                    else:
                        colors[neighbor]=1-colors[current]
                        queue.append(neighbor)
        used=defaultdict(set)
        week=date.fromisoformat(day).isocalendar()[:2]
        for s in sorted(rows,key=lambda s:(colors[s["session_id"]],-int(s["duration_minutes"]),s["session_id"])):
            duration=int(s["duration_minutes"])
            slot=f"DEMO-{day}-"+("AM" if colors[s["session_id"]]==0 else "PM")
            assigned={}
            for role in ["teacher","assistant","key_coach"]:
                candidates=[p for p in data["People"] if p["role"]==role and av[(p["person_id"],slot)]==1
                    and p["person_id"] not in used[slot] and loads[(p["person_id"],week)]+duration<=int(p["max_minutes_week"])]
                if not candidates:
                    raise ValueError("Không tạo được bố trí demo cho "+s["session_id"]+" / "+role)
                p=min(candidates,key=lambda p:(loads[(p["person_id"],week)],p["person_id"]))
                assigned[role]=p["person_id"]
                loads[(p["person_id"],week)]+=duration
                used[slot].add(p["person_id"])
            room=next((r for r in s["allowed_rooms"].split("|") if "room:"+r not in used[slot]),None)
            if not room:
                raise ValueError("Không đủ phòng trong bố trí demo "+slot)
            used[slot].add("room:"+room)
            _,start,_=slot_time(slots[slot]); end=start+duration
            result.append(dict(session_id=s["session_id"],class_id=s["class_id"],subject=s["subject"],slot_id=slot,
                date=day,start=f"{start//60:02}:{start%60:02}",end=f"{end//60:02}:{end%60:02}",
                teacher_id=assigned["teacher"],assistant_ids=assigned["assistant"],key_coach_id=assigned["key_coach"],room_id=room,locked="0"))
    errors=validate_solution(data,result)
    if errors:
        raise ValueError("Bố trí demo chưa hợp lệ: "+str(errors[:3]))
    return result


def complete_demo(source):
    original=read_tables(source)
    data={k:deepcopy(original.get(k,[])) for k in SCHEMA}
    if not data["People"] or not data["Sessions"]:
        raise ValueError("Cần workbook People và Sessions đã nhập từ dữ liệu nguồn.")
    old_slots={s["slot_id"]:s for s in data["Slots"]}
    dates_by_session={s["session_id"]:old_slots[s["baseline_slot"]]["date"] for s in data["Sessions"]}
    days=sorted(set(dates_by_session.values()))
    planning=[]
    for day in days:
        for part,start,end in [("AM","09:00","13:00"),("PM","14:00","18:00")]:
            planning.append(dict(slot_id=f"DEMO-{day}-{part}",date=day,start=start,end=end))
    # Preserve original slots as provenance, but make them unavailable in this new scenario.
    data["Slots"]=data["Slots"]+planning
    subjects=sorted({s["subject"] for s in data["Sessions"]})
    staff=sorted((p for p in data["People"] if p["role"]!="student"),key=lambda p:p["person_id"])
    coaches=[p for p in staff if p["role"] in {"assistant","key_coach"}]
    key_ids={p["person_id"] for p in coaches[:12]}
    for person in staff:
        # Values are demo policies, not facts inferred from source assignments.
        person["max_minutes_day"]=480
        person["max_minutes_week"]=1200
        if person["role"]=="teacher":
            person["subjects"]="|".join(subjects)
        else:
            person["role"]="key_coach" if person["person_id"] in key_ids else "assistant"
            person["skills"]="DEMO_SUPPORT"
    learners=sorted((p for p in data["People"] if p["role"]=="student"),key=lambda p:p["person_id"])
    classes=["L3A","L3B","L2A","L2B"]
    membership={cls:[] for cls in classes}
    for index,person in enumerate(learners):
        membership[classes[index%len(classes)]].append(person["person_id"])
    membership["L3AB"]=membership["L3A"]+membership["L3B"]
    membership["L2AB"]=membership["L2A"]+membership["L2B"]
    membership["L2A+B"]=membership["L2AB"]
    used_classes={s["class_id"] for s in data["Sessions"]}
    if not used_classes<=membership.keys():
        raise ValueError("Chưa có quy tắc giả lập cho lớp: "+str(used_classes-membership.keys()))
    data["Enrollments"]=[dict(person_id=pid,class_id=cls) for cls in sorted(used_classes) for pid in membership[cls]]
    for room in data["Rooms"]:
        room["capacity"]=max(len(ids) for cls,ids in membership.items() if cls in used_classes)
    room_ids=sorted(r["room_id"] for r in data["Rooms"])
    choices={cls:[room_ids[2*i],room_ids[2*i+1]] for i,cls in enumerate(classes)}
    choices["L3AB"]=[room_ids[0],room_ids[2]]
    choices["L2AB"]=choices["L2A+B"]=[room_ids[4],room_ids[6]]
    changes=[]
    for session in data["Sessions"]:
        day=dates_by_session[session["session_id"]]
        changes.append(dict(session_id=session["session_id"],source_locked=text(session.get("locked")),
                            demo_locked="0",reason="New synthetic scenario only; original locked schedule unchanged"))
        session.update(assistant_count=1,key_coach_required=1,required_skill="DEMO_SUPPORT",locked=0,
                       allowed_slots=f"DEMO-{day}-AM|DEMO-{day}-PM",allowed_rooms="|".join(choices[session["class_id"]]))
        for key in ["baseline_slot","baseline_teacher","baseline_assistants","baseline_key_coach","baseline_room"]:
            session[key]=""
    plan_ids={s["slot_id"] for s in planning}
    teams={}
    for role in ["teacher","assistant","key_coach"]:
        for index,p in enumerate(sorted((p for p in staff if p["role"]==role),key=lambda p:p["person_id"])[:12]):
            teams[p["person_id"]]="AM" if index%2==0 else "PM"
    data["Availability"]=[dict(person_id=p["person_id"],slot_id=s["slot_id"],
        available=int(s["slot_id"] in plan_ids and (p["role"]=="student" or s["slot_id"].endswith("-"+teams.get(p["person_id"],"NONE")))),
        preferred=int(s["slot_id"].endswith("-AM"))) for p in data["People"] for s in data["Slots"]]
    notes=[
        dict(field="scenario",assumption="SYNTHETIC DEMO ONLY. These are not real enrolments, capacities, qualifications, availability or approved schedules."),
        dict(field="source",assumption=str(Path(source).name)+". Source workbook and production workspace are preserved."),
        dict(field="staff_limits",assumption="480 minutes/day, 1200 minutes/ISO week for all teaching staff; demo policy."),
        dict(field="qualifications",assumption="All source teachers qualified for all source subjects; only for this synthetic scenario."),
        dict(field="coach_skills",assumption="All coaches have DEMO_SUPPORT; first 12 sorted coach IDs serve as key coaches."),
        dict(field="enrolments",assumption="Sorted learners assigned round-robin to L3A,L3B,L2A,L2B; merged classes contain the union. No source evidence for these memberships."),
        dict(field="room_capacity",assumption="All rooms have synthetic capacity equal to the largest demo merged class; not a statement about real rooms."),
        dict(field="availability",assumption="All students available in both demo slots per source date. First 12 IDs per staff role are active, alternating AM/PM teams; others reserve and unavailable. Original slots unavailable. AM preferred. All synthetic."),
        dict(field="room_candidates",assumption="Two sorted source room IDs per class are candidate demo rooms. This is a synthetic planning restriction, not an actual room assignment."),
        dict(field="sessions",assumption="Each source session stays on its source date; solver chooses 09:00-13:00 or 14:00-18:00, one teacher, one lab coach and one key coach."),
        dict(field="locks",assumption="New demo sessions are unlocked drafts. A feasible synthetic initial arrangement is used as a warm start, not an approved real schedule. Original source locks remain unchanged."),
    ]
    problems=readiness(data)
    if problems:
        raise ValueError("Demo preparation still missing data: "+str(problems[:5]))
    initial=seed_schedule(data)
    sessions={s["session_id"]:s for s in data["Sessions"]}
    for row in initial:
        target=sessions[row["session_id"]]
        for field,key in [("baseline_slot","slot_id"),("baseline_teacher","teacher_id"),("baseline_assistants","assistant_ids"),("baseline_key_coach","key_coach_id"),("baseline_room","room_id")]:
            target[field]=row[key]
    return data, {"Assumptions":notes,"Source_Sessions":original["Sessions"],"Source_Rooms":original["Rooms"],"Demo_Changes":changes,"Demo_Initial":initial}


def write_complete_demo(source,target):
    data,notes=complete_demo(source)
    atomic_write(target,data|notes,SCHEMA)
    return data
