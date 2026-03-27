from __future__ import annotations

from typing import Final

STORE_VERSION: Final[int] = 1

SUBJECT_TYPES: Final[tuple[str, ...]] = ("Theory", "Lab")
ROOM_TYPES: Final[tuple[str, ...]] = ("Classroom", "Lab")
RANKS: Final[tuple[str, ...]] = (
    "Assistant Professor",
    "Associate Professor",
    "Professor",
    "Visiting Faculty",
)
BATCHES: Final[tuple[str, ...]] = ("B1", "B2", "B3", "B4")
WEEKDAYS: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
)
TEACHING_SLOT_LABELS: Final[tuple[str, ...]] = (
    "09:00-10:00",
    "10:00-11:00",
    "11:00-12:00",
    "12:00-13:00",
    "14:00-15:00",
    "15:00-16:00",
    "16:00-17:00",
)
LAB_BLOCKS: Final[tuple[tuple[int, int], ...]] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (4, 5),
    (5, 6),
)
LAB_BLOCK_LABELS: Final[dict[tuple[int, int], str]] = {
    (0, 1): "09:00-11:00",
    (1, 2): "10:00-12:00",
    (2, 3): "11:00-13:00",
    (4, 5): "14:00-16:00",
    (5, 6): "15:00-17:00",
}
MAX_DAILY_SECTION_HOURS: Final[int] = 7
MAX_PREFERRED_SUBJECTS: Final[int] = 3
LAST_SLOT_INDEX: Final[int] = 6
WORKING_DAYS_PER_WEEK: Final[int] = 5
TOTAL_SECTION_WEEKLY_CAPACITY: Final[int] = MAX_DAILY_SECTION_HOURS * WORKING_DAYS_PER_WEEK
FULL_DAY_SLOT_COUNT: Final[int] = len(TEACHING_SLOT_LABELS)

RANK_WEIGHTS: Final[dict[str, float]] = {
    "Professor": 1.30,
    "Associate Professor": 1.15,
    "Assistant Professor": 1.00,
    "Visiting Faculty": 0.85,
}


def span_slots(start_slot: int, duration: int) -> tuple[int, ...]:
    return tuple(start_slot + offset for offset in range(duration))


def slot_label(slot_index: int) -> str:
    return TEACHING_SLOT_LABELS[slot_index]


def slot_labels_for_span(start_slot: int, duration: int) -> tuple[str, ...]:
    return tuple(slot_label(index) for index in span_slots(start_slot, duration))
