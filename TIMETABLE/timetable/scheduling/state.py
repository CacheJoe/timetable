from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from timetable.constants import BATCHES, WEEKDAYS, span_slots
from timetable.models import AppState, ScheduleEntry, Teacher, new_id


@dataclass(slots=True)
class TheoryDemand:
    demand_id: str
    section_id: str
    subject_id: str
    sequence_no: int


@dataclass(slots=True)
class LabDemand:
    demand_id: str
    section_id: str
    rotation_index: int
    batch_subject_map: dict[str, str]


@dataclass(slots=True)
class PlacedItem:
    item_id: str
    kind: str
    section_id: str
    day: str
    slots: tuple[int, ...]
    entries: list[ScheduleEntry]
    score: float
    demand: TheoryDemand | LabDemand
    subject_ids: tuple[str, ...]
    teacher_ids: tuple[str, ...]
    room_ids: tuple[str, ...]


@dataclass(slots=True)
class SchedulerLookups:
    teachers_by_id: dict[str, Teacher]
    subject_type_by_id: dict[str, str]
    section_semester_by_id: dict[str, int]


@dataclass(slots=True)
class SchedulerState:
    app_state: AppState
    lookups: SchedulerLookups
    teacher_busy: dict[str, dict[str, set[int]]] = field(default_factory=dict)
    room_busy: dict[str, dict[str, set[int]]] = field(default_factory=dict)
    section_busy: dict[str, dict[str, set[int]]] = field(default_factory=dict)
    teacher_loads: dict[str, int] = field(default_factory=dict)
    teacher_subjects: dict[str, set[str]] = field(default_factory=dict)
    teacher_day_loads: dict[str, dict[str, int]] = field(default_factory=dict)
    section_day_loads: dict[str, dict[str, int]] = field(default_factory=dict)
    section_subject_day_sessions: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    teacher_section_subject_counts: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    lab_completion: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    placed_items: dict[str, PlacedItem] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.teacher_busy = {
            teacher.id: {day: set() for day in WEEKDAYS}
            for teacher in self.app_state.teachers
        }
        self.room_busy = {
            room.id: {day: set() for day in WEEKDAYS}
            for room in self.app_state.rooms
        }
        self.section_busy = {
            section.id: {day: set() for day in WEEKDAYS}
            for section in self.app_state.sections
        }
        self.teacher_loads = {teacher.id: 0 for teacher in self.app_state.teachers}
        self.teacher_subjects = {teacher.id: set() for teacher in self.app_state.teachers}
        self.teacher_day_loads = {
            teacher.id: {day: 0 for day in WEEKDAYS}
            for teacher in self.app_state.teachers
        }
        self.section_day_loads = {
            section.id: {day: 0 for day in WEEKDAYS}
            for section in self.app_state.sections
        }
        self.section_subject_day_sessions = defaultdict(lambda: defaultdict(lambda: {day: 0 for day in WEEKDAYS}))
        self.teacher_section_subject_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.lab_completion = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for section in self.app_state.sections:
            for batch in BATCHES:
                self.lab_completion[section.id][batch] = defaultdict(int)

    def item_slots(self, start_slot: int, duration: int) -> tuple[int, ...]:
        return span_slots(start_slot, duration)

    def resource_free(self, resource_map: dict[str, dict[str, set[int]]], resource_id: str, day: str, slots: tuple[int, ...]) -> bool:
        return all(slot not in resource_map[resource_id][day] for slot in slots)

    def section_can_take(self, section_id: str, day: str, slots: tuple[int, ...], max_daily_hours: int) -> bool:
        if not self.resource_free(self.section_busy, section_id, day, slots):
            return False
        return (self.section_day_loads[section_id][day] + len(slots)) <= max_daily_hours

    def teacher_can_take(self, teacher_id: str, subject_id: str, day: str, slots: tuple[int, ...], hours: int) -> bool:
        teacher = self.lookups.teachers_by_id[teacher_id]
        if not self.resource_free(self.teacher_busy, teacher_id, day, slots):
            return False
        if self.teacher_loads[teacher_id] + hours > teacher.max_weekly_load:
            return False
        current_subjects = self.teacher_subjects[teacher_id]
        if subject_id in current_subjects:
            return True
        return len(current_subjects) < teacher.max_subjects

    def room_can_take(self, room_id: str, day: str, slots: tuple[int, ...]) -> bool:
        return self.resource_free(self.room_busy, room_id, day, slots)

    def place_item(self, item: PlacedItem) -> None:
        self.placed_items[item.item_id] = item
        self.section_day_loads[item.section_id][item.day] += len(item.slots)
        for subject_id in set(item.subject_ids):
            self.section_subject_day_sessions[item.section_id][subject_id][item.day] += 1
        for entry in item.entries:
            slots = self.item_slots(entry.start_slot, entry.duration)
            for slot in slots:
                self.teacher_busy[entry.teacher_id][entry.day].discard(slot)
                self.room_busy[entry.room_id][entry.day].discard(slot)
                self.section_busy[entry.section_id][entry.day].discard(slot)
            self.teacher_loads[entry.teacher_id] += entry.duration
            self.teacher_subjects[entry.teacher_id].add(entry.subject_id)
            self.teacher_day_loads[entry.teacher_id][entry.day] += entry.duration
            self.teacher_section_subject_counts[entry.teacher_id][entry.section_id][entry.subject_id] += 1
            if entry.batch:
                self.lab_completion[entry.section_id][entry.batch][entry.subject_id] += 1

    def remove_item(self, item_id: str) -> PlacedItem:
        item = self.placed_items.pop(item_id)
        self.section_day_loads[item.section_id][item.day] -= len(item.slots)
        for subject_id in set(item.subject_ids):
            self.section_subject_day_sessions[item.section_id][subject_id][item.day] -= 1
        for entry in item.entries:
            slots = self.item_slots(entry.start_slot, entry.duration)
            for slot in slots:
                self.teacher_busy[entry.teacher_id][entry.day].remove(slot)
                self.room_busy[entry.room_id][entry.day].remove(slot)
                self.section_busy[entry.section_id][entry.day].remove(slot)
            self.teacher_loads[entry.teacher_id] -= entry.duration
            self.teacher_day_loads[entry.teacher_id][entry.day] -= entry.duration
            self.teacher_section_subject_counts[entry.teacher_id][entry.section_id][entry.subject_id] -= 1
            if self.teacher_section_subject_counts[entry.teacher_id][entry.section_id][entry.subject_id] <= 0:
                del self.teacher_section_subject_counts[entry.teacher_id][entry.section_id][entry.subject_id]
            if entry.batch:
                self.lab_completion[entry.section_id][entry.batch][entry.subject_id] -= 1
                if self.lab_completion[entry.section_id][entry.batch][entry.subject_id] <= 0:
                    del self.lab_completion[entry.section_id][entry.batch][entry.subject_id]

        self._rebuild_teacher_subjects()
        return item

    def _rebuild_teacher_subjects(self) -> None:
        self.teacher_subjects = {teacher.id: set() for teacher in self.app_state.teachers}
        for item in self.placed_items.values():
            for entry in item.entries:
                self.teacher_subjects[entry.teacher_id].add(entry.subject_id)

    def build_theory_item(
        self,
        demand: TheoryDemand,
        day: str,
        start_slot: int,
        teacher_id: str,
        room_id: str,
        score: float,
    ) -> PlacedItem:
        entry = ScheduleEntry(
            id=new_id("entry"),
            entry_type="Theory",
            section_id=demand.section_id,
            day=day,
            start_slot=start_slot,
            duration=1,
            subject_id=demand.subject_id,
            teacher_id=teacher_id,
            room_id=room_id,
        )
        return PlacedItem(
            item_id=demand.demand_id,
            kind="theory",
            section_id=demand.section_id,
            day=day,
            slots=(start_slot,),
            entries=[entry],
            score=score,
            demand=demand,
            subject_ids=(demand.subject_id,),
            teacher_ids=(teacher_id,),
            room_ids=(room_id,),
        )

    def build_lab_item(
        self,
        demand: LabDemand,
        day: str,
        start_slot: int,
        assignments: list[tuple[str, str, str, str]],
        score: float,
    ) -> PlacedItem:
        cluster_id = new_id("cluster")
        entries = []
        for batch, subject_id, teacher_id, room_id in assignments:
            entries.append(
                ScheduleEntry(
                    id=new_id("entry"),
                    entry_type="Lab",
                    section_id=demand.section_id,
                    day=day,
                    start_slot=start_slot,
                    duration=2,
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    room_id=room_id,
                    batch=batch,
                    cluster_id=cluster_id,
                )
            )
        return PlacedItem(
            item_id=demand.demand_id,
            kind="lab",
            section_id=demand.section_id,
            day=day,
            slots=span_slots(start_slot, 2),
            entries=entries,
            score=score,
            demand=demand,
            subject_ids=tuple(entry.subject_id for entry in entries),
            teacher_ids=tuple(entry.teacher_id for entry in entries),
            room_ids=tuple(entry.room_id for entry in entries),
        )

    def sorted_entries(self) -> list[ScheduleEntry]:
        return sorted(
            [entry for item in self.placed_items.values() for entry in item.entries],
            key=lambda entry: (entry.section_id, entry.day, entry.start_slot, entry.batch or ""),
        )
