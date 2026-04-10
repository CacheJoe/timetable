from __future__ import annotations

from collections import defaultdict

from timetable.constants import BATCHES, TEACHING_SLOT_LABELS, WEEKDAYS, span_slots
from timetable.models import AppState, ScheduleEntry


def _lookup_maps(app_state: AppState) -> dict[str, dict[str, str]]:
    return {
        "subjects": {subject.id: subject.name for subject in app_state.subjects},
        "teachers": {teacher.id: teacher.name for teacher in app_state.teachers},
        "rooms": {room.id: room.name for room in app_state.rooms},
        "sections": {section.id: section.name for section in app_state.sections},
    }


def _group_entries_by_resource(
    app_state: AppState,
) -> tuple[
    dict[str, dict[str, dict[int, list[ScheduleEntry]]]],
    dict[str, dict[str, dict[int, list[ScheduleEntry]]]],
    dict[str, dict[str, dict[int, list[ScheduleEntry]]]],
]:
    if not app_state.generated_timetable:
        return {}, {}, {}

    section_grid: dict[str, dict[str, dict[int, list[ScheduleEntry]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    teacher_grid: dict[str, dict[str, dict[int, list[ScheduleEntry]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    room_grid: dict[str, dict[str, dict[int, list[ScheduleEntry]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for entry in app_state.generated_timetable.entries:
        for slot in span_slots(entry.start_slot, entry.duration):
            section_grid[entry.section_id][entry.day][slot].append(entry)
            teacher_grid[entry.teacher_id][entry.day][slot].append(entry)
            room_grid[entry.room_id][entry.day][slot].append(entry)

    return section_grid, teacher_grid, room_grid


def _format_section_cell(entries: list[ScheduleEntry], names: dict[str, dict[str, str]]) -> str:
    if not entries:
        return ""

    entries = sorted(entries, key=lambda entry: (entry.entry_type != "Lab", entry.batch or ""))
    if entries[0].entry_type == "Theory":
        entry = entries[0]
        return f"{names['subjects'][entry.subject_id]}\n{names['teachers'][entry.teacher_id]}\n{names['rooms'][entry.room_id]}"

    lines: list[str] = []
    grouped_by_batch = {entry.batch: entry for entry in entries if entry.batch}
    for batch in BATCHES:
        entry = grouped_by_batch.get(batch)
        if not entry:
            continue
        lines.append(
            f"{batch}: {names['subjects'][entry.subject_id]} | {names['teachers'][entry.teacher_id]} | {names['rooms'][entry.room_id]}"
        )
    return "\n".join(lines)


def _format_teacher_cell(entries: list[ScheduleEntry], names: dict[str, dict[str, str]]) -> str:
    if not entries:
        return ""

    entries = sorted(entries, key=lambda entry: (entry.entry_type != "Lab", names["sections"][entry.section_id], entry.batch or ""))
    lines: list[str] = []
    for entry in entries:
        label = f"{names['sections'][entry.section_id]} | {names['subjects'][entry.subject_id]} | {names['rooms'][entry.room_id]}"
        if entry.batch:
            label = f"{label} | {entry.batch}"
        lines.append(label)
    return "\n".join(lines)


def build_section_tables(app_state: AppState) -> dict[str, list[dict[str, str]]]:
    if not app_state.generated_timetable:
        return {}

    names = _lookup_maps(app_state)
    section_grid, _, _ = _group_entries_by_resource(app_state)
    tables: dict[str, list[dict[str, str]]] = {}

    for section in app_state.sections:
        rows: list[dict[str, str]] = []
        for day in WEEKDAYS:
            row = {"Day": day}
            for slot_index, slot_label in enumerate(TEACHING_SLOT_LABELS):
                row[slot_label] = _format_section_cell(section_grid[section.id][day][slot_index], names)
            rows.append(row)
        tables[section.name] = rows
    return tables


def build_teacher_tables(app_state: AppState) -> dict[str, list[dict[str, str]]]:
    if not app_state.generated_timetable:
        return {}

    names = _lookup_maps(app_state)
    _, teacher_grid, _ = _group_entries_by_resource(app_state)
    tables: dict[str, list[dict[str, str]]] = {}

    for teacher in app_state.teachers:
        rows: list[dict[str, str]] = []
        for day in WEEKDAYS:
            row = {"Day": day}
            for slot_index, slot_label in enumerate(TEACHING_SLOT_LABELS):
                row[slot_label] = _format_teacher_cell(teacher_grid[teacher.id][day][slot_index], names)
            rows.append(row)
        tables[teacher.name] = rows
    return tables


def _format_room_cell(entries: list[ScheduleEntry], names: dict[str, dict[str, str]]) -> str:
    if not entries:
        return ""

    entries = sorted(entries, key=lambda entry: (names["sections"][entry.section_id], entry.batch or ""))
    lines: list[str] = []
    for entry in entries:
        label = f"{names['sections'][entry.section_id]} | {names['subjects'][entry.subject_id]} | {names['teachers'][entry.teacher_id]}"
        if entry.batch:
            label = f"{label} | {entry.batch}"
        lines.append(label)
    return "\n".join(lines)


def build_room_tables(app_state: AppState) -> dict[str, list[dict[str, str]]]:
    if not app_state.generated_timetable:
        return {}

    names = _lookup_maps(app_state)
    _, _, room_grid = _group_entries_by_resource(app_state)
    tables: dict[str, list[dict[str, str]]] = {}

    for room in app_state.rooms:
        rows: list[dict[str, str]] = []
        room_label = f"{room.name} ({room.room_type})"
        for day in WEEKDAYS:
            row = {"Day": day}
            for slot_index, slot_label in enumerate(TEACHING_SLOT_LABELS):
                row[slot_label] = _format_room_cell(room_grid[room.id][day][slot_index], names)
            rows.append(row)
        tables[room_label] = rows
    return tables


def build_teacher_load_rows(app_state: AppState) -> list[dict[str, str | int]]:
    loads = app_state.generated_timetable.teacher_loads if app_state.generated_timetable else {}
    teacher_subjects = app_state.generated_timetable.teacher_subjects if app_state.generated_timetable else {}
    subject_names = {subject.id: subject.name for subject in app_state.subjects}

    rows: list[dict[str, str | int]] = []
    for teacher in app_state.teachers:
        rows.append(
            {
                "Teacher": teacher.name,
                "Rank": teacher.rank,
                "Target Load": teacher.target_weekly_load,
                "Max Load": teacher.max_weekly_load,
                "Current Load": loads.get(teacher.id, 0),
                "Subjects": ", ".join(subject_names.get(subject_id, subject_id) for subject_id in teacher_subjects.get(teacher.id, [])),
            }
        )
    return rows


def build_lab_completion_rows(app_state: AppState) -> list[dict[str, str | int]]:
    if not app_state.generated_timetable:
        return []

    section_names = {section.id: section.name for section in app_state.sections}
    subject_names = {subject.id: subject.name for subject in app_state.subjects}
    rows: list[dict[str, str | int]] = []

    for section_id, batch_map in app_state.generated_timetable.lab_completion.items():
        for batch, subject_map in batch_map.items():
            for subject_id, count in subject_map.items():
                rows.append(
                    {
                        "Section": section_names.get(section_id, section_id),
                        "Batch": batch,
                        "Lab Subject": subject_names.get(subject_id, subject_id),
                        "Completed Sessions": count,
                    }
                )
    return rows


def build_room_occupancy_rows(app_state: AppState) -> list[dict[str, str | int]]:
    if not app_state.generated_timetable:
        return []

    room_hours: dict[str, int] = defaultdict(int)
    for entry in app_state.generated_timetable.entries:
        room_hours[entry.room_id] += entry.duration

    rows: list[dict[str, str | int]] = []
    for room in sorted(app_state.rooms, key=lambda item: (item.room_type, item.name)):
        rows.append(
            {
                "Room": room.name,
                "Type": room.room_type,
                "Occupied Hours": room_hours.get(room.id, 0),
            }
        )
    return rows


def rows_to_matrix(rows: list[dict[str, str | int]]) -> list[list[str]]:
    if not rows:
        return [[]]
    headers = list(rows[0].keys())
    matrix: list[list[str]] = [headers]
    for row in rows:
        matrix.append([str(row.get(header, "")) for header in headers])
    return matrix
