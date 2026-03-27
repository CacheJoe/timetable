from __future__ import annotations

from collections import Counter, defaultdict

from timetable.constants import BATCHES, FULL_DAY_SLOT_COUNT, MAX_DAILY_SECTION_HOURS, TOTAL_SECTION_WEEKLY_CAPACITY
from timetable.models import AppState


def _duplicate_names(items: list[str]) -> list[str]:
    return [name for name, count in Counter(items).items() if count > 1]


def validate_store_integrity(state: AppState) -> list[str]:
    errors: list[str] = []

    teacher_duplicates = _duplicate_names([teacher.name.casefold() for teacher in state.teachers])
    if teacher_duplicates:
        errors.append("Teacher names must be unique.")

    subject_keys = [f"{subject.semester}|{subject.name.casefold()}|{subject.subject_type}" for subject in state.subjects]
    if _duplicate_names(subject_keys):
        errors.append("Subject name/type combinations must be unique within a semester.")

    section_duplicates = _duplicate_names([section.name.casefold() for section in state.sections])
    if section_duplicates:
        errors.append("Section names must be unique.")

    room_duplicates = _duplicate_names([room.name.casefold() for room in state.rooms])
    if room_duplicates:
        errors.append("Room names must be unique.")

    subject_type_by_id = {subject.id: subject.subject_type for subject in state.subjects}
    for teacher in state.teachers:
        for subject_id in teacher.preferred_theory_subject_ids:
            if subject_id not in subject_type_by_id:
                errors.append(f"Teacher '{teacher.name}' references an unknown theory subject.")
        for subject_id in teacher.preferred_lab_subject_ids:
            if subject_id not in subject_type_by_id:
                errors.append(f"Teacher '{teacher.name}' references an unknown lab subject.")

    return errors


def generation_precheck(state: AppState) -> tuple[list[str], list[str]]:
    errors = validate_store_integrity(state)
    warnings: list[str] = []

    if not state.sections:
        errors.append("At least one section is required.")
    if not state.subjects:
        errors.append("At least one subject is required.")
    if not state.teachers:
        errors.append("At least one teacher is required.")
    if not state.rooms:
        errors.append("At least one room is required.")

    classrooms = [room for room in state.rooms if room.room_type == "Classroom"]
    labs = [room for room in state.rooms if room.room_type == "Lab"]

    subject_by_semester: dict[int, list] = defaultdict(list)
    for subject in state.subjects:
        subject_by_semester[subject.semester].append(subject)

    total_teacher_capacity = sum(teacher.max_weekly_load for teacher in state.teachers)
    total_teacher_demand = 0
    total_classroom_hours = 0
    total_lab_room_hours = 0

    if any(subject.subject_type == "Theory" for subject in state.subjects) and not classrooms:
        errors.append("At least one classroom is required to schedule theory subjects.")
    if any(subject.subject_type == "Lab" for subject in state.subjects):
        if len(labs) < len(BATCHES):
            errors.append("At least four lab rooms are required because each batch uses a separate lab room.")
        if len(state.teachers) < len(BATCHES):
            errors.append("At least four teachers are required to run a lab slot because each batch needs a faculty member.")

    for section in state.sections:
        semester_subjects = subject_by_semester.get(section.semester, [])
        if not semester_subjects:
            errors.append(f"Section '{section.name}' has no subjects mapped to semester {section.semester}.")
            continue

        section_total_hours = sum(subject.weekly_hours for subject in semester_subjects)
        if section_total_hours > TOTAL_SECTION_WEEKLY_CAPACITY:
            errors.append(
                f"Section '{section.name}' requires {section_total_hours} hours, which exceeds the weekly capacity of {TOTAL_SECTION_WEEKLY_CAPACITY}."
            )
        if section_total_hours > MAX_DAILY_SECTION_HOURS * 5:
            errors.append(f"Section '{section.name}' exceeds the weekly section capacity.")

        lab_subjects = [subject for subject in semester_subjects if subject.subject_type == "Lab"]
        if lab_subjects and len(lab_subjects) < 2:
            errors.append(
                f"Semester {section.semester} needs at least two lab subjects to satisfy the parallel two-subject lab rule."
            )

        total_classroom_hours += sum(subject.weekly_hours for subject in semester_subjects if subject.subject_type == "Theory")
        total_lab_room_hours += sum(subject.weekly_hours for subject in lab_subjects) * len(BATCHES)
        total_teacher_demand += sum(subject.weekly_hours for subject in semester_subjects if subject.subject_type == "Theory")
        total_teacher_demand += sum(subject.weekly_hours for subject in lab_subjects) * len(BATCHES)

    classroom_capacity = len(classrooms) * FULL_DAY_SLOT_COUNT * 5
    lab_room_capacity = len(labs) * FULL_DAY_SLOT_COUNT * 5

    if total_classroom_hours > classroom_capacity:
        errors.append(
            f"Classroom capacity is insufficient. Need {total_classroom_hours} room-hours, but only {classroom_capacity} are available."
        )
    if total_lab_room_hours > lab_room_capacity:
        errors.append(
            f"Lab room capacity is insufficient. Need {total_lab_room_hours} room-hours, but only {lab_room_capacity} are available."
        )
    if total_teacher_demand > total_teacher_capacity:
        errors.append(
            f"Teacher load capacity is insufficient. Need {total_teacher_demand} teaching-hours, but teachers allow only {total_teacher_capacity}."
        )

    if total_teacher_capacity > 0 and total_teacher_demand < total_teacher_capacity * 0.35:
        warnings.append("Teacher capacity is far above demand. Load balancing will still work, but many teachers may remain lightly used.")

    if len(classrooms) == 1:
        warnings.append("Only one classroom is available, so theory scheduling may be tighter than usual.")

    return errors, warnings
