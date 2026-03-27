from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from timetable.constants import BATCHES, MAX_PREFERRED_SUBJECTS, RANKS, ROOM_TYPES, STORE_VERSION, SUBJECT_TYPES


class ModelValidationError(ValueError):
    """Raised when a domain model violates a hard rule."""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _clean_string(value: str) -> str:
    return value.strip()


@dataclass(slots=True)
class Subject:
    id: str
    name: str
    subject_type: str
    semester: int
    weekly_hours: int

    def validate(self) -> None:
        self.name = _clean_string(self.name)
        if not self.name:
            raise ModelValidationError("Subject name is required.")
        if self.subject_type not in SUBJECT_TYPES:
            raise ModelValidationError("Subject type must be Theory or Lab.")
        if self.semester < 1:
            raise ModelValidationError("Semester must be at least 1.")
        if self.weekly_hours < 1:
            raise ModelValidationError("Weekly hours must be positive.")
        if self.subject_type == "Lab" and self.weekly_hours % 2 != 0:
            raise ModelValidationError("Lab weekly hours must be even because labs are 2-hour blocks.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Subject":
        subject = cls(
            id=payload.get("id") or new_id("sub"),
            name=str(payload.get("name", "")),
            subject_type=str(payload.get("subject_type", "Theory")),
            semester=int(payload.get("semester", 1)),
            weekly_hours=int(payload.get("weekly_hours", 1)),
        )
        subject.validate()
        return subject


@dataclass(slots=True)
class Teacher:
    id: str
    name: str
    rank: str
    max_weekly_load: int
    target_weekly_load: int
    max_subjects: int
    preferred_theory_subject_ids: list[str] = field(default_factory=list)
    preferred_lab_subject_ids: list[str] = field(default_factory=list)
    preferred_slots: list[str] = field(default_factory=list)

    def validate(self, subject_type_by_id: dict[str, str] | None = None) -> None:
        self.name = _clean_string(self.name)
        if not self.name:
            raise ModelValidationError("Teacher name is required.")
        if self.rank not in RANKS:
            raise ModelValidationError("Invalid teacher rank.")
        if self.max_weekly_load < 1:
            raise ModelValidationError("Maximum weekly load must be positive.")
        if self.target_weekly_load < 0:
            raise ModelValidationError("Target weekly load cannot be negative.")
        if self.target_weekly_load > self.max_weekly_load:
            raise ModelValidationError("Target weekly load cannot exceed maximum weekly load.")
        if self.max_subjects < 1:
            raise ModelValidationError("Maximum number of subjects must be at least 1.")
        if len(self.preferred_theory_subject_ids) > MAX_PREFERRED_SUBJECTS:
            raise ModelValidationError("Preferred theory subject selections are limited to 3.")
        if len(self.preferred_lab_subject_ids) > MAX_PREFERRED_SUBJECTS:
            raise ModelValidationError("Preferred lab subject selections are limited to 3.")
        if subject_type_by_id is not None:
            for subject_id in self.preferred_theory_subject_ids:
                if subject_type_by_id.get(subject_id) != "Theory":
                    raise ModelValidationError("Preferred theory subjects must reference stored theory subjects.")
            for subject_id in self.preferred_lab_subject_ids:
                if subject_type_by_id.get(subject_id) != "Lab":
                    raise ModelValidationError("Preferred lab subjects must reference stored lab subjects.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any], subject_type_by_id: dict[str, str] | None = None) -> "Teacher":
        teacher = cls(
            id=payload.get("id") or new_id("teach"),
            name=str(payload.get("name", "")),
            rank=str(payload.get("rank", RANKS[0])),
            max_weekly_load=int(payload.get("max_weekly_load", 18)),
            target_weekly_load=int(payload.get("target_weekly_load", 14)),
            max_subjects=int(payload.get("max_subjects", 3)),
            preferred_theory_subject_ids=[str(item) for item in payload.get("preferred_theory_subject_ids", [])],
            preferred_lab_subject_ids=[str(item) for item in payload.get("preferred_lab_subject_ids", [])],
            preferred_slots=[str(item) for item in payload.get("preferred_slots", [])],
        )
        teacher.validate(subject_type_by_id)
        return teacher


@dataclass(slots=True)
class Section:
    id: str
    name: str
    semester: int

    def validate(self) -> None:
        self.name = _clean_string(self.name)
        if not self.name:
            raise ModelValidationError("Section name is required.")
        if self.semester < 1:
            raise ModelValidationError("Semester must be at least 1.")

    @property
    def batches(self) -> tuple[str, ...]:
        return BATCHES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Section":
        section = cls(
            id=payload.get("id") or new_id("sec"),
            name=str(payload.get("name", "")),
            semester=int(payload.get("semester", 1)),
        )
        section.validate()
        return section


@dataclass(slots=True)
class Room:
    id: str
    name: str
    room_type: str

    def validate(self) -> None:
        self.name = _clean_string(self.name)
        if not self.name:
            raise ModelValidationError("Room name is required.")
        if self.room_type not in ROOM_TYPES:
            raise ModelValidationError("Room type must be Classroom or Lab.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Room":
        room = cls(
            id=payload.get("id") or new_id("room"),
            name=str(payload.get("name", "")),
            room_type=str(payload.get("room_type", ROOM_TYPES[0])),
        )
        room.validate()
        return room


@dataclass(slots=True)
class ScheduleEntry:
    id: str
    entry_type: str
    section_id: str
    day: str
    start_slot: int
    duration: int
    subject_id: str
    teacher_id: str
    room_id: str
    batch: str | None = None
    cluster_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScheduleEntry":
        return cls(
            id=str(payload["id"]),
            entry_type=str(payload["entry_type"]),
            section_id=str(payload["section_id"]),
            day=str(payload["day"]),
            start_slot=int(payload["start_slot"]),
            duration=int(payload["duration"]),
            subject_id=str(payload["subject_id"]),
            teacher_id=str(payload["teacher_id"]),
            room_id=str(payload["room_id"]),
            batch=payload.get("batch"),
            cluster_id=payload.get("cluster_id"),
        )


@dataclass(slots=True)
class GeneratedTimetable:
    id: str
    generated_at: str
    attempt_count: int
    seed: int
    total_soft_score: float
    entries: list[ScheduleEntry]
    teacher_loads: dict[str, int]
    teacher_subjects: dict[str, list[str]]
    lab_completion: dict[str, dict[str, dict[str, int]]]
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [entry.to_dict() for entry in self.entries]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeneratedTimetable":
        return cls(
            id=str(payload["id"]),
            generated_at=str(payload["generated_at"]),
            attempt_count=int(payload.get("attempt_count", 1)),
            seed=int(payload.get("seed", 0)),
            total_soft_score=float(payload.get("total_soft_score", 0.0)),
            entries=[ScheduleEntry.from_dict(item) for item in payload.get("entries", [])],
            teacher_loads={str(key): int(value) for key, value in payload.get("teacher_loads", {}).items()},
            teacher_subjects={
                str(key): [str(subject_id) for subject_id in value]
                for key, value in payload.get("teacher_subjects", {}).items()
            },
            lab_completion={
                str(section_id): {
                    str(batch): {str(subject_id): int(count) for subject_id, count in subject_map.items()}
                    for batch, subject_map in batch_map.items()
                }
                for section_id, batch_map in payload.get("lab_completion", {}).items()
            },
            diagnostics=[str(item) for item in payload.get("diagnostics", [])],
        )

    @classmethod
    def create(
        cls,
        attempt_count: int,
        seed: int,
        total_soft_score: float,
        entries: list[ScheduleEntry],
        teacher_loads: dict[str, int],
        teacher_subjects: dict[str, list[str]],
        lab_completion: dict[str, dict[str, dict[str, int]]],
        diagnostics: list[str] | None = None,
    ) -> "GeneratedTimetable":
        return cls(
            id=new_id("tt"),
            generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            attempt_count=attempt_count,
            seed=seed,
            total_soft_score=total_soft_score,
            entries=entries,
            teacher_loads=teacher_loads,
            teacher_subjects=teacher_subjects,
            lab_completion=lab_completion,
            diagnostics=diagnostics or [],
        )


@dataclass(slots=True)
class AppState:
    version: int
    teachers: list[Teacher]
    subjects: list[Subject]
    sections: list[Section]
    rooms: list[Room]
    generated_timetable: GeneratedTimetable | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "teachers": [teacher.to_dict() for teacher in self.teachers],
            "subjects": [subject.to_dict() for subject in self.subjects],
            "sections": [section.to_dict() for section in self.sections],
            "rooms": [room.to_dict() for room in self.rooms],
            "generated_timetable": self.generated_timetable.to_dict() if self.generated_timetable else None,
        }

    @classmethod
    def empty(cls) -> "AppState":
        return cls(version=STORE_VERSION, teachers=[], subjects=[], sections=[], rooms=[], generated_timetable=None)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppState":
        raw_subjects = payload.get("subjects", [])
        subjects = [Subject.from_dict(item) for item in raw_subjects]
        subject_type_by_id = {subject.id: subject.subject_type for subject in subjects}
        teachers = [Teacher.from_dict(item, subject_type_by_id) for item in payload.get("teachers", [])]
        sections = [Section.from_dict(item) for item in payload.get("sections", [])]
        rooms = [Room.from_dict(item) for item in payload.get("rooms", [])]
        generated = payload.get("generated_timetable")
        timetable = GeneratedTimetable.from_dict(generated) if generated else None
        return cls(
            version=int(payload.get("version", STORE_VERSION)),
            teachers=teachers,
            subjects=subjects,
            sections=sections,
            rooms=rooms,
            generated_timetable=timetable,
        )
