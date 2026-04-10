from __future__ import annotations

import json
from pathlib import Path

from timetable.constants import STORE_VERSION
from timetable.models import AppState, GeneratedTimetable, Room, Section, Subject, Teacher
from timetable.validation import validate_store_integrity


class JsonRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.data_dir = self.root / "data"
        self.store_path = self.data_dir / "store.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.save_state(AppState.empty())

    def load_state(self) -> AppState:
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        return AppState.from_dict(raw)

    def save_state(self, state: AppState) -> None:
        state.version = STORE_VERSION
        errors = validate_store_integrity(state)
        if errors:
            raise ValueError("\n".join(errors))
        payload = state.to_dict()
        temp_path = self.store_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.store_path)

    def replace_with_demo_state(self, state: AppState) -> None:
        state.generated_timetable = None
        self.save_state(state)

    def clear_generated_timetable(self) -> None:
        state = self.load_state()
        state.generated_timetable = None
        self.save_state(state)

    def save_generated_timetable(self, timetable: GeneratedTimetable) -> None:
        state = self.load_state()
        state.generated_timetable = timetable
        self.save_state(state)

    def upsert_subject(self, subject: Subject) -> None:
        state = self.load_state()
        updated = False
        for index, existing in enumerate(state.subjects):
            if existing.id == subject.id:
                state.subjects[index] = subject
                updated = True
                break
        if not updated:
            state.subjects.append(subject)
        state.generated_timetable = None
        self.save_state(state)

    def delete_subject(self, subject_id: str) -> None:
        state = self.load_state()
        state.subjects = [subject for subject in state.subjects if subject.id != subject_id]
        for teacher in state.teachers:
            teacher.preferred_theory_subject_ids = [item for item in teacher.preferred_theory_subject_ids if item != subject_id]
            teacher.preferred_lab_subject_ids = [item for item in teacher.preferred_lab_subject_ids if item != subject_id]
        state.generated_timetable = None
        self.save_state(state)

    def upsert_teacher(self, teacher: Teacher) -> None:
        state = self.load_state()
        updated = False
        for index, existing in enumerate(state.teachers):
            if existing.id == teacher.id:
                state.teachers[index] = teacher
                updated = True
                break
        if not updated:
            state.teachers.append(teacher)
        state.generated_timetable = None
        self.save_state(state)

    def delete_teacher(self, teacher_id: str) -> None:
        state = self.load_state()
        state.teachers = [teacher for teacher in state.teachers if teacher.id != teacher_id]
        state.generated_timetable = None
        self.save_state(state)

    def upsert_section(self, section: Section) -> None:
        state = self.load_state()
        updated = False
        for index, existing in enumerate(state.sections):
            if existing.id == section.id:
                state.sections[index] = section
                updated = True
                break
        if not updated:
            state.sections.append(section)
        state.generated_timetable = None
        self.save_state(state)

    def delete_section(self, section_id: str) -> None:
        state = self.load_state()
        state.sections = [section for section in state.sections if section.id != section_id]
        state.generated_timetable = None
        self.save_state(state)

    def upsert_room(self, room: Room) -> None:
        state = self.load_state()
        updated = False
        for index, existing in enumerate(state.rooms):
            if existing.id == room.id:
                state.rooms[index] = room
                updated = True
                break
        if not updated:
            state.rooms.append(room)
        state.generated_timetable = None
        self.save_state(state)

    def delete_room(self, room_id: str) -> None:
        state = self.load_state()
        state.rooms = [room for room in state.rooms if room.id != room_id]
        state.generated_timetable = None
        self.save_state(state)
