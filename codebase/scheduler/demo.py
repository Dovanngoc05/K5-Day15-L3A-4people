"""Small fully synthetic dataset with explicit availability, no inferred facts."""
from .excel import DEFAULT_WEIGHTS, empty_data


def demo_data():
    data = empty_data()
    for pid, name, role, subjects, skills in [
        ("T01", "Giảng viên mẫu A", "teacher", "Python|AI", ""),
        ("T02", "Giảng viên mẫu B", "teacher", "Python|AI", ""),
        ("A01", "Lab coach mẫu A", "assistant", "", "python|ai"),
        ("A02", "Lab coach mẫu B", "assistant", "", "python|ai"),
        ("K01", "Key coach mẫu", "key_coach", "", "python|ai"),
        ("L0001", "Học viên mẫu 1", "student", "", ""),
        ("L0002", "Học viên mẫu 2", "student", "", ""),
        ("L0003", "Học viên mẫu 3", "student", "", ""),
    ]:
        data["People"].append(dict(person_id=pid, name=name, role=role, subjects=subjects,
                                   skills=skills, max_minutes_day=240, max_minutes_week=720))
    for day in ("2027-04-19", "2027-04-20"):
        for start, end, part in [("09:00", "11:00", "S"), ("14:00", "16:00", "C")]:
            data["Slots"].append(dict(slot_id=day + "-" + part, date=day, start=start, end=end))
    data["Rooms"] = [dict(room_id="H209", capacity=40), dict(room_id="H210", capacity=30)]
    data["Enrollments"] = [dict(person_id="L0001", class_id="L3A"),
                            dict(person_id="L0002", class_id="L3A"),
                            dict(person_id="L0003", class_id="L3B")]
    for i, (cls, subject, skill) in enumerate([("L3A", "Python", "python"), ("L3A", "AI", "ai"), ("L3B", "Python", "python")], 1):
        data["Sessions"].append(dict(session_id=f"LAB-{i}", class_id=cls, subject=subject,
            duration_minutes=120, required_skill=skill, assistant_count=1, key_coach_required=1,
            locked=0, baseline_slot="", baseline_teacher="", baseline_assistants="", baseline_key_coach="", baseline_room=""))
    for person in data["People"]:
        for slot in data["Slots"]:
            data["Availability"].append(dict(person_id=person["person_id"], slot_id=slot["slot_id"],
                                            available=1, preferred=int(slot["start"] == "09:00")))
    data["Weights"] = [dict(constraint_id=k, weight=v) for k, v in DEFAULT_WEIGHTS.items()]
    return data
