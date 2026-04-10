from __future__ import annotations

from timetable.constants import LAST_SLOT_INDEX, RANK_WEIGHTS, slot_labels_for_span
from timetable.models import Teacher


def _segments() -> tuple[tuple[int, ...], ...]:
    return ((0, 1, 2, 3), (4, 5, 6))


def gap_count(occupied_slots: set[int]) -> int:
    gaps = 0
    for segment in _segments():
        active = [slot for slot in segment if slot in occupied_slots]
        if len(active) < 2:
            continue
        for slot in range(min(active), max(active) + 1):
            if slot not in occupied_slots and slot in segment:
                gaps += 1
    return gaps


def max_consecutive_run(occupied_slots: set[int]) -> int:
    longest = 0
    for segment in _segments():
        run = 0
        for slot in segment:
            if slot in occupied_slots:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return longest


def adjacency_bonus(occupied_slots: set[int], new_slots: tuple[int, ...]) -> float:
    bonus = 0.0
    for slot in new_slots:
        if slot - 1 in occupied_slots:
            bonus += 4.0
        if slot + 1 in occupied_slots:
            bonus += 4.0
    return bonus


def gap_delta(occupied_slots: set[int], new_slots: tuple[int, ...]) -> int:
    after = set(occupied_slots)
    after.update(new_slots)
    return gap_count(after) - gap_count(occupied_slots)


def consecutive_penalty(occupied_slots: set[int], new_slots: tuple[int, ...]) -> float:
    after = set(occupied_slots)
    after.update(new_slots)
    longest = max_consecutive_run(after)
    if longest <= 3:
        return 0.0
    return float((longest - 3) * 6)


def preferred_subject_score(teacher: Teacher, subject_id: str, subject_type: str) -> float:
    preferences = (
        teacher.preferred_theory_subject_ids if subject_type == "Theory" else teacher.preferred_lab_subject_ids
    )
    if subject_id not in preferences:
        return 0.0
    position = preferences.index(subject_id)
    return 28.0 - (position * 4.0)


def preferred_slot_score(teacher: Teacher, start_slot: int, duration: int) -> float:
    labels = slot_labels_for_span(start_slot, duration)
    score = 0.0
    for label in labels:
        if label in teacher.preferred_slots:
            score += 7.5
    return score


def load_target_improvement(current_load: int, target_load: int, assignment_hours: int) -> float:
    before = abs(current_load - target_load)
    after = abs((current_load + assignment_hours) - target_load)
    return float((before - after) * 4)


def last_slot_penalty(slots: tuple[int, ...]) -> float:
    if LAST_SLOT_INDEX in slots:
        return 10.0
    return 0.0


def rank_slot_bonus(rank: str, slots: tuple[int, ...]) -> float:
    weight = RANK_WEIGHTS.get(rank, 1.0)
    if LAST_SLOT_INDEX in slots:
        return -6.0 * weight
    if min(slots) <= 2:
        return 5.0 * weight
    return 3.0 * weight

