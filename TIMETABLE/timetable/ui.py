from __future__ import annotations

from pathlib import Path

import streamlit as st

from timetable.constants import MAX_PREFERRED_SUBJECTS, RANKS, ROOM_TYPES, SUBJECT_TYPES, TEACHING_SLOT_LABELS
from timetable.exports.csv_export import room_csv_zip_bytes, section_csv_zip_bytes, teacher_csv_zip_bytes
from timetable.exports.xlsx_export import room_workbook_bytes, section_workbook_bytes, teacher_workbook_bytes
from timetable.models import Room, Section, Subject, Teacher, new_id
from timetable.reporting import (
    build_lab_completion_rows,
    build_room_occupancy_rows,
    build_room_tables,
    build_section_tables,
    build_teacher_load_rows,
    build_teacher_tables,
)
from timetable.sample_data import build_demo_state
from timetable.scheduling.generator import GenerationError, TimetableGenerator
from timetable.storage import JsonRepository
from timetable.validation import generation_precheck, validate_store_integrity


def _rerun() -> None:
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun")
    rerun()


def _subject_label_map(subjects: list[Subject]) -> dict[str, str]:
    return {
        subject.id: f"S{subject.semester} | {subject.name} ({subject.subject_type}, {subject.weekly_hours}h)"
        for subject in sorted(subjects, key=lambda item: (item.semester, item.subject_type, item.name))
    }


def _teacher_rows(state) -> list[dict[str, str | int]]:
    subject_names = {subject.id: subject.name for subject in state.subjects}
    loads = state.generated_timetable.teacher_loads if state.generated_timetable else {}
    rows = []
    for teacher in state.teachers:
        rows.append(
            {
                "Name": teacher.name,
                "Rank": teacher.rank,
                "Max Load": teacher.max_weekly_load,
                "Target Load": teacher.target_weekly_load,
                "Current Load": loads.get(teacher.id, 0),
                "Max Subjects": teacher.max_subjects,
                "Preferred Theory": ", ".join(subject_names.get(subject_id, subject_id) for subject_id in teacher.preferred_theory_subject_ids),
                "Preferred Lab": ", ".join(subject_names.get(subject_id, subject_id) for subject_id in teacher.preferred_lab_subject_ids),
                "Preferred Slots": ", ".join(teacher.preferred_slots),
            }
        )
    return rows


def _subject_rows(state) -> list[dict[str, str | int]]:
    return [
        {
            "Name": subject.name,
            "Type": subject.subject_type,
            "Semester": subject.semester,
            "Weekly Hours": subject.weekly_hours,
        }
        for subject in sorted(state.subjects, key=lambda item: (item.semester, item.subject_type, item.name))
    ]


def _section_rows(state) -> list[dict[str, str | int]]:
    return [
        {
            "Name": section.name,
            "Semester": section.semester,
            "Lab Batches": "B1, B2, B3, B4",
        }
        for section in sorted(state.sections, key=lambda item: (item.semester, item.name))
    ]


def _room_rows(state) -> list[dict[str, str]]:
    return [
        {"Name": room.name, "Type": room.room_type}
        for room in sorted(state.rooms, key=lambda item: (item.room_type, item.name))
    ]


def _save_subject(repo: JsonRepository, subject_id: str | None, name: str, subject_type: str, semester: int, weekly_hours: int) -> None:
    subject = Subject(
        id=subject_id or new_id("sub"),
        name=name,
        subject_type=subject_type,
        semester=semester,
        weekly_hours=weekly_hours,
    )
    subject.validate()
    repo.upsert_subject(subject)


def _save_teacher(
    repo: JsonRepository,
    state,
    teacher_id: str | None,
    name: str,
    rank: str,
    max_weekly_load: int,
    target_weekly_load: int,
    max_subjects: int,
    preferred_theory_subject_ids: list[str],
    preferred_lab_subject_ids: list[str],
    preferred_slots: list[str],
) -> None:
    if len(preferred_theory_subject_ids) > MAX_PREFERRED_SUBJECTS or len(preferred_lab_subject_ids) > MAX_PREFERRED_SUBJECTS:
        raise ValueError("Preferred subject selections are limited to 3 per subject type.")
    teacher = Teacher(
        id=teacher_id or new_id("teach"),
        name=name,
        rank=rank,
        max_weekly_load=max_weekly_load,
        target_weekly_load=target_weekly_load,
        max_subjects=max_subjects,
        preferred_theory_subject_ids=preferred_theory_subject_ids,
        preferred_lab_subject_ids=preferred_lab_subject_ids,
        preferred_slots=preferred_slots,
    )
    teacher.validate({subject.id: subject.subject_type for subject in state.subjects})
    repo.upsert_teacher(teacher)


def _save_section(repo: JsonRepository, section_id: str | None, name: str, semester: int) -> None:
    section = Section(id=section_id or new_id("sec"), name=name, semester=semester)
    section.validate()
    repo.upsert_section(section)


def _save_room(repo: JsonRepository, room_id: str | None, name: str, room_type: str) -> None:
    room = Room(id=room_id or new_id("room"), name=name, room_type=room_type)
    room.validate()
    repo.upsert_room(room)


def _render_subjects(repo: JsonRepository, state) -> None:
    st.subheader("Subjects")
    st.dataframe(_subject_rows(state), use_container_width=True, hide_index=True)

    add_box, edit_box = st.columns(2)
    with add_box:
        with st.form("add_subject_form", clear_on_submit=True):
            st.markdown("**Add Subject**")
            name = st.text_input("Name")
            subject_type = st.selectbox("Type", SUBJECT_TYPES)
            semester = st.number_input("Semester", min_value=1, step=1, value=1)
            weekly_hours = st.number_input("Weekly Required Hours", min_value=1, step=1, value=3)
            submitted = st.form_submit_button("Save Subject")
            if submitted:
                try:
                    _save_subject(repo, None, name, subject_type, int(semester), int(weekly_hours))
                    st.success("Subject saved.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    with edit_box:
        st.markdown("**Edit Subject**")
        if not state.subjects:
            st.info("Add a subject to enable editing.")
            return
        selected_id = st.selectbox(
            "Stored Subjects",
            options=[subject.id for subject in state.subjects],
            format_func=lambda item: _subject_label_map(state.subjects)[item],
            key="edit_subject_select",
        )
        subject = next(item for item in state.subjects if item.id == selected_id)
        with st.form("edit_subject_form"):
            name = st.text_input("Name", value=subject.name)
            subject_type = st.selectbox("Type", SUBJECT_TYPES, index=SUBJECT_TYPES.index(subject.subject_type))
            semester = st.number_input("Semester", min_value=1, step=1, value=subject.semester)
            weekly_hours = st.number_input("Weekly Required Hours", min_value=1, step=1, value=subject.weekly_hours)
            submitted = st.form_submit_button("Update Subject")
            if submitted:
                try:
                    _save_subject(repo, subject.id, name, subject_type, int(semester), int(weekly_hours))
                    st.success("Subject updated.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        if st.button("Delete Subject", key=f"delete_subject_{subject.id}", type="secondary"):
            repo.delete_subject(subject.id)
            st.success("Subject deleted.")
            _rerun()


def _render_teachers(repo: JsonRepository, state) -> None:
    st.subheader("Teachers")
    st.dataframe(_teacher_rows(state), use_container_width=True, hide_index=True)
    subject_labels = _subject_label_map(state.subjects)
    theory_ids = [subject.id for subject in state.subjects if subject.subject_type == "Theory"]
    lab_ids = [subject.id for subject in state.subjects if subject.subject_type == "Lab"]

    add_box, edit_box = st.columns(2)
    with add_box:
        with st.form("add_teacher_form", clear_on_submit=True):
            st.markdown("**Add Teacher**")
            name = st.text_input("Name")
            rank = st.selectbox("Rank", RANKS)
            max_weekly_load = st.number_input("Maximum Weekly Load", min_value=1, step=1, value=18)
            target_weekly_load = st.number_input("Target Weekly Load", min_value=0, step=1, value=14)
            max_subjects = st.number_input("Maximum Subjects Allowed", min_value=1, step=1, value=3)
            preferred_theory = st.multiselect(
                "Preferred Theory Subjects (max 3)",
                options=theory_ids,
                format_func=lambda item: subject_labels[item],
            )
            preferred_lab = st.multiselect(
                "Preferred Lab Subjects (max 3)",
                options=lab_ids,
                format_func=lambda item: subject_labels[item],
            )
            preferred_slots = st.multiselect("Preferred Teaching Hours", options=list(TEACHING_SLOT_LABELS))
            submitted = st.form_submit_button("Save Teacher")
            if submitted:
                try:
                    _save_teacher(
                        repo,
                        state,
                        None,
                        name,
                        rank,
                        int(max_weekly_load),
                        int(target_weekly_load),
                        int(max_subjects),
                        preferred_theory,
                        preferred_lab,
                        preferred_slots,
                    )
                    st.success("Teacher saved.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    with edit_box:
        st.markdown("**Edit Teacher**")
        if not state.teachers:
            st.info("Add a teacher to enable editing.")
            return
        selected_id = st.selectbox(
            "Stored Teachers",
            options=[teacher.id for teacher in state.teachers],
            format_func=lambda item: next(teacher.name for teacher in state.teachers if teacher.id == item),
            key="edit_teacher_select",
        )
        teacher = next(item for item in state.teachers if item.id == selected_id)
        with st.form("edit_teacher_form"):
            name = st.text_input("Name", value=teacher.name)
            rank = st.selectbox("Rank", RANKS, index=RANKS.index(teacher.rank))
            max_weekly_load = st.number_input("Maximum Weekly Load", min_value=1, step=1, value=teacher.max_weekly_load)
            target_weekly_load = st.number_input("Target Weekly Load", min_value=0, step=1, value=teacher.target_weekly_load)
            max_subjects = st.number_input("Maximum Subjects Allowed", min_value=1, step=1, value=teacher.max_subjects)
            preferred_theory = st.multiselect(
                "Preferred Theory Subjects (max 3)",
                options=theory_ids,
                default=[subject_id for subject_id in teacher.preferred_theory_subject_ids if subject_id in theory_ids],
                format_func=lambda item: subject_labels[item],
                key=f"edit_theory_{teacher.id}",
            )
            preferred_lab = st.multiselect(
                "Preferred Lab Subjects (max 3)",
                options=lab_ids,
                default=[subject_id for subject_id in teacher.preferred_lab_subject_ids if subject_id in lab_ids],
                format_func=lambda item: subject_labels[item],
                key=f"edit_lab_{teacher.id}",
            )
            preferred_slots = st.multiselect(
                "Preferred Teaching Hours",
                options=list(TEACHING_SLOT_LABELS),
                default=teacher.preferred_slots,
                key=f"edit_slots_{teacher.id}",
            )
            submitted = st.form_submit_button("Update Teacher")
            if submitted:
                try:
                    _save_teacher(
                        repo,
                        state,
                        teacher.id,
                        name,
                        rank,
                        int(max_weekly_load),
                        int(target_weekly_load),
                        int(max_subjects),
                        preferred_theory,
                        preferred_lab,
                        preferred_slots,
                    )
                    st.success("Teacher updated.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        if st.button("Delete Teacher", key=f"delete_teacher_{teacher.id}", type="secondary"):
            repo.delete_teacher(teacher.id)
            st.success("Teacher deleted.")
            _rerun()


def _render_sections(repo: JsonRepository, state) -> None:
    st.subheader("Sections")
    st.dataframe(_section_rows(state), use_container_width=True, hide_index=True)

    add_box, edit_box = st.columns(2)
    with add_box:
        with st.form("add_section_form", clear_on_submit=True):
            st.markdown("**Add Section**")
            name = st.text_input("Name")
            semester = st.number_input("Semester", min_value=1, step=1, value=1, key="add_section_semester")
            submitted = st.form_submit_button("Save Section")
            if submitted:
                try:
                    _save_section(repo, None, name, int(semester))
                    st.success("Section saved.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    with edit_box:
        st.markdown("**Edit Section**")
        if not state.sections:
            st.info("Add a section to enable editing.")
            return
        selected_id = st.selectbox(
            "Stored Sections",
            options=[section.id for section in state.sections],
            format_func=lambda item: next(section.name for section in state.sections if section.id == item),
            key="edit_section_select",
        )
        section = next(item for item in state.sections if item.id == selected_id)
        with st.form("edit_section_form"):
            name = st.text_input("Name", value=section.name)
            semester = st.number_input("Semester", min_value=1, step=1, value=section.semester, key="edit_section_semester")
            submitted = st.form_submit_button("Update Section")
            if submitted:
                try:
                    _save_section(repo, section.id, name, int(semester))
                    st.success("Section updated.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        if st.button("Delete Section", key=f"delete_section_{section.id}", type="secondary"):
            repo.delete_section(section.id)
            st.success("Section deleted.")
            _rerun()


def _render_rooms(repo: JsonRepository, state) -> None:
    st.subheader("Rooms")
    st.dataframe(_room_rows(state), use_container_width=True, hide_index=True)

    add_box, edit_box = st.columns(2)
    with add_box:
        with st.form("add_room_form", clear_on_submit=True):
            st.markdown("**Add Room**")
            name = st.text_input("Name")
            room_type = st.selectbox("Type", ROOM_TYPES)
            submitted = st.form_submit_button("Save Room")
            if submitted:
                try:
                    _save_room(repo, None, name, room_type)
                    st.success("Room saved.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    with edit_box:
        st.markdown("**Edit Room**")
        if not state.rooms:
            st.info("Add a room to enable editing.")
            return
        selected_id = st.selectbox(
            "Stored Rooms",
            options=[room.id for room in state.rooms],
            format_func=lambda item: next(room.name for room in state.rooms if room.id == item),
            key="edit_room_select",
        )
        room = next(item for item in state.rooms if item.id == selected_id)
        with st.form("edit_room_form"):
            name = st.text_input("Name", value=room.name)
            room_type = st.selectbox("Type", ROOM_TYPES, index=ROOM_TYPES.index(room.room_type))
            submitted = st.form_submit_button("Update Room")
            if submitted:
                try:
                    _save_room(repo, room.id, name, room_type)
                    st.success("Room updated.")
                    _rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        if st.button("Delete Room", key=f"delete_room_{room.id}", type="secondary"):
            repo.delete_room(room.id)
            st.success("Room deleted.")
            _rerun()


def _render_dashboard(state) -> None:
    st.subheader("Overview")
    issues = validate_store_integrity(state)
    metric_columns = st.columns(5)
    metric_columns[0].metric("Teachers", len(state.teachers))
    metric_columns[1].metric("Subjects", len(state.subjects))
    metric_columns[2].metric("Sections", len(state.sections))
    metric_columns[3].metric("Rooms", len(state.rooms))
    metric_columns[4].metric("Timetable", "Available" if state.generated_timetable else "Not Generated")

    if issues:
        for issue in issues:
            st.error(issue)
    else:
        st.success("Stored data passed structural validation.")

    if state.generated_timetable:
        st.info(
            f"Latest timetable soft score: {state.generated_timetable.total_soft_score} | "
            f"Attempts: {state.generated_timetable.attempt_count} | "
            f"Generated At: {state.generated_timetable.generated_at}"
        )
    else:
        st.caption("Generate a timetable after populating subjects, teachers, sections, and rooms.")


def _render_generation(repo: JsonRepository, state) -> None:
    st.subheader("Generation")
    errors, warnings = generation_precheck(state)
    if warnings:
        for warning in warnings:
            st.warning(warning)
    if errors:
        for error in errors:
            st.error(error)
        return

    with st.form("generation_form"):
        max_attempts = st.number_input("Maximum Generation Attempts", min_value=1, step=1, value=24)
        seed_value = st.text_input("Seed (optional)", value="")
        submitted = st.form_submit_button("Generate Timetable")
        if submitted:
            generator = TimetableGenerator()
            try:
                timetable = generator.generate(
                    state,
                    max_attempts=int(max_attempts),
                    seed=int(seed_value) if seed_value.strip() else None,
                )
                repo.save_generated_timetable(timetable)
                st.success("Timetable generated successfully.")
                _rerun()
            except GenerationError as exc:
                st.error(str(exc))


def _render_results(state) -> None:
    st.subheader("Results")
    if not state.generated_timetable:
        st.info("No generated timetable is available yet.")
        return

    if state.generated_timetable.diagnostics:
        with st.expander("Generation Diagnostics", expanded=False):
            for line in state.generated_timetable.diagnostics:
                st.write(f"- {line}")

    result_tabs = st.tabs(["Section View", "Teacher View", "Room Occupancy", "Loads & Rotation", "Exports"])

    with result_tabs[0]:
        section_tables = build_section_tables(state)
        selected = st.selectbox("Section", options=list(section_tables.keys()), key="result_section_select")
        st.dataframe(section_tables[selected], use_container_width=True, hide_index=True)

    with result_tabs[1]:
        teacher_tables = build_teacher_tables(state)
        selected = st.selectbox("Teacher", options=list(teacher_tables.keys()), key="result_teacher_select")
        st.dataframe(teacher_tables[selected], use_container_width=True, hide_index=True)

    with result_tabs[2]:
        room_tables = build_room_tables(state)
        selected = st.selectbox("Room", options=list(room_tables.keys()), key="result_room_select")
        st.dataframe(room_tables[selected], use_container_width=True, hide_index=True)
        st.markdown("**Room Occupancy Summary**")
        st.dataframe(build_room_occupancy_rows(state), use_container_width=True, hide_index=True)

    with result_tabs[3]:
        st.markdown("**Teacher Loads**")
        st.dataframe(build_teacher_load_rows(state), use_container_width=True, hide_index=True)
        st.markdown("**Lab Completion Tracking**")
        st.dataframe(build_lab_completion_rows(state), use_container_width=True, hide_index=True)

    with result_tabs[4]:
        st.download_button(
            "Download Section Timetables (Excel)",
            data=section_workbook_bytes(state),
            file_name="section_timetables.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Download Teacher Timetables (Excel)",
            data=teacher_workbook_bytes(state),
            file_name="teacher_timetables.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Download Section Timetables (CSV Zip)",
            data=section_csv_zip_bytes(state),
            file_name="section_timetables_csv.zip",
            mime="application/zip",
        )
        st.download_button(
            "Download Teacher Timetables (CSV Zip)",
            data=teacher_csv_zip_bytes(state),
            file_name="teacher_timetables_csv.zip",
            mime="application/zip",
        )
        st.download_button(
            "Download Room Occupancy (Excel)",
            data=room_workbook_bytes(state),
            file_name="room_occupancy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Download Room Occupancy (CSV Zip)",
            data=room_csv_zip_bytes(state),
            file_name="room_occupancy_csv.zip",
            mime="application/zip",
        )


def render_app(repo: JsonRepository, root: Path) -> None:
    st.title("Timetable Management System")
    st.caption("Single-branch academic timetable planner with hard constraints, soft optimization, lab rotation, and exports.")

    state = repo.load_state()

    with st.sidebar:
        st.markdown("**Data Actions**")
        if st.button("Load Demo Data", use_container_width=True):
            repo.replace_with_demo_state(build_demo_state())
            _rerun()
        if st.button("Clear Generated Timetable", use_container_width=True, disabled=not state.generated_timetable):
            repo.clear_generated_timetable()
            _rerun()
        st.caption(f"Workspace: {root}")

    tabs = st.tabs(["Dashboard", "Subjects", "Teachers", "Sections", "Rooms", "Generate", "Results"])

    with tabs[0]:
        _render_dashboard(state)
    with tabs[1]:
        _render_subjects(repo, state)
    with tabs[2]:
        _render_teachers(repo, state)
    with tabs[3]:
        _render_sections(repo, state)
    with tabs[4]:
        _render_rooms(repo, state)
    with tabs[5]:
        _render_generation(repo, state)
    with tabs[6]:
        _render_results(state)
