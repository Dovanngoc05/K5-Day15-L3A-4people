"""Build teacher profile updates from the local schedule extraction report."""
from collections import defaultdict
import json

from .excel import split, text
from .solver import integer, slot_time


REPORT_NAME = "schedule-extraction.json"
LIMITS = {"max_minutes_day": 1440, "max_minutes_week": 10080}
STAFF_ROLES = {"teacher", "assistant", "key_coach"}


def fill_report_profiles(path, data):
    """Fill blank fields on matching staff in an import preview."""
    try:
        with path.open(encoding="utf-8-sig") as source:
            report = json.load(source)
    except FileNotFoundError:
        return []
    profiles = {p["person_id"]: p for p in report["tables"]["People"]
                if p["role"] in STAFF_ROLES}
    updates = []
    for person in data["People"]:
        pid = person["person_id"]
        profile = profiles.get(pid)
        role = person["role"]
        if (not profile or role not in STAFF_ROLES
                or (role == "teacher") != (profile["role"] == "teacher")):
            continue
        changes = {}
        for field in ("subjects", "skills", *LIMITS):
            value = text(profile.get(field))
            if value and not text(person.get(field)):
                changes[field] = integer(value, field, 1, LIMITS[field]) if field in LIMITS else value
        if changes:
            person.update(changes)
            updates.append(dict(person_id=pid, role=role, **changes))
    return updates


def teacher_profile_updates(path, data):
    with path.open(encoding="utf-8-sig") as source:
        report = json.load(source)
    tables = report["tables"]
    teachers = {p["person_id"]: p for p in data["People"] if p["role"] == "teacher"}
    source_profiles = {p["person_id"]: p for p in tables["People"] if p["role"] == "teacher"}
    slots = {row["slot_id"]: row for row in tables["Slots"]}
    observations = defaultdict(set)
    for row in report.get("teaching_observations", []):
        observations[row["session_id"], row["date"]].update(row["teachers"])

    subjects = defaultdict(set)
    daily = defaultdict(lambda: defaultdict(int))
    weekly = defaultdict(lambda: defaultdict(int))
    counted = set()
    for row in tables["Sessions"]:
        slot = slots.get(row.get("baseline_slot"))
        if not slot:
            continue
        day, start, end = slot_time(slot)
        minutes = integer(row["duration_minutes"], "duration_minutes", 1, 1440)
        if minutes > end - start:
            continue
        subject = text(row.get("subject"))
        key = (row["session_id"], day.isoformat())
        assigned = observations.get(key) or split(row.get("baseline_teacher"))
        for pid in assigned & teachers.keys():
            assignment = (pid, key)
            if assignment in counted:
                continue
            counted.add(assignment)
            if subject:
                subjects[pid].add(subject)
            daily[pid][day] += minutes
            weekly[pid][day.isocalendar()[:2]] += minutes

    updates = {}
    for pid, current in sorted(teachers.items()):
        source = source_profiles.get(pid, {})
        values = {
            "subjects": text(source.get("subjects")) or "|".join(sorted(subjects[pid])),
            "skills": text(source.get("skills")),
        }
        for field, loads, ceiling in (
            ("max_minutes_day", daily, LIMITS["max_minutes_day"]),
            ("max_minutes_week", weekly, LIMITS["max_minutes_week"]),
        ):
            declared = text(source.get(field))
            observed = max(loads[pid].values(), default=0)
            if declared:
                values[field] = integer(declared, field, 1, ceiling)
            elif 0 < observed <= ceiling:
                values[field] = observed
        changes = {field: value for field, value in values.items()
                   if value and not text(current.get(field))}
        if changes:
            updates[pid] = changes
    return updates
