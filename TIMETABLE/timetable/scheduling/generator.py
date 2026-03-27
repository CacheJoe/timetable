from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from timetable.constants import BATCHES, LAB_BLOCKS, MAX_DAILY_SECTION_HOURS, WEEKDAYS
from timetable.models import AppState, GeneratedTimetable, Room, Section, Subject, Teacher, new_id
from timetable.scheduling.scoring import (
    adjacency_bonus,
    consecutive_penalty,
    gap_delta,
    last_slot_penalty,
    load_target_improvement,
    preferred_slot_score,
    preferred_subject_score,
    rank_slot_bonus,
)
from timetable.scheduling.state import LabDemand, PlacedItem, SchedulerLookups, SchedulerState, TheoryDemand
from timetable.validation import generation_precheck


class GenerationError(RuntimeError):
    """Raised when the generator cannot find a valid timetable."""


@dataclass(slots=True)
class TheoryCandidate:
    day: str
    start_slot: int
    teacher_id: str
    room_id: str
    score: float


@dataclass(slots=True)
class LabCandidate:
    day: str
    start_slot: int
    assignments: list[tuple[str, str, str, str]]
    score: float


class TimetableGenerator:
    def generate(self, app_state: AppState, max_attempts: int = 24, seed: int | None = None) -> GeneratedTimetable:
        errors, warnings = generation_precheck(app_state)
        if errors:
            raise GenerationError("\n".join(errors))

        seed_value = seed if seed is not None else random.SystemRandom().randint(1_000, 999_999)
        subjects_by_id = {subject.id: subject for subject in app_state.subjects}
        teachers_by_id = {teacher.id: teacher for teacher in app_state.teachers}
        sections_by_id = {section.id: section for section in app_state.sections}
        subjects_by_semester: dict[int, list[Subject]] = defaultdict(list)
        for subject in app_state.subjects:
            subjects_by_semester[subject.semester].append(subject)

        lookups = SchedulerLookups(
            teachers_by_id=teachers_by_id,
            subject_type_by_id={subject.id: subject.subject_type for subject in app_state.subjects},
            section_semester_by_id={section.id: section.semester for section in app_state.sections},
        )

        diagnostics: list[str] = list(warnings)
        last_failure = "Generator exhausted all retries."

        for attempt in range(1, max_attempts + 1):
            rng = random.Random(seed_value + (attempt * 31))
            state = SchedulerState(app_state=app_state, lookups=lookups)

            section_order = app_state.sections[:]
            rng.shuffle(section_order)
            section_order.sort(
                key=lambda section: (
                    -sum(subject.weekly_hours for subject in subjects_by_semester[section.semester] if subject.subject_type == "Lab"),
                    -sum(subject.weekly_hours for subject in subjects_by_semester[section.semester]),
                )
            )

            try:
                for section in section_order:
                    lab_demands = self._build_lab_demands_for_section(
                        section=section,
                        semester_subjects=subjects_by_semester[section.semester],
                        rng=rng,
                    )
                    if lab_demands and not self._schedule_section_labs(
                        section=section,
                        lab_demands=lab_demands,
                        state=state,
                        teachers=app_state.teachers,
                        lab_rooms=[room for room in app_state.rooms if room.room_type == "Lab"],
                        rng=rng,
                    ):
                        raise GenerationError(f"Could not place lab blocks for section {section.name} on attempt {attempt}.")

                theory_demands = self._build_theory_demands(
                    sections=app_state.sections,
                    subjects_by_semester=subjects_by_semester,
                )
                if not self._schedule_theory_demands(
                    demands=theory_demands,
                    state=state,
                    teachers=app_state.teachers,
                    classrooms=[room for room in app_state.rooms if room.room_type == "Classroom"],
                    rng=rng,
                ):
                    raise GenerationError(f"Could not complete theory scheduling on attempt {attempt}.")

                total_soft_score = round(sum(item.score for item in state.placed_items.values()), 2)
                diagnostics.append(f"Generated successfully on attempt {attempt} with seed {seed_value}.")
                return GeneratedTimetable.create(
                    attempt_count=attempt,
                    seed=seed_value,
                    total_soft_score=total_soft_score,
                    entries=state.sorted_entries(),
                    teacher_loads=dict(state.teacher_loads),
                    teacher_subjects={teacher_id: sorted(subject_ids) for teacher_id, subject_ids in state.teacher_subjects.items()},
                    lab_completion={
                        section_id: {
                            batch: dict(subject_map)
                            for batch, subject_map in batch_map.items()
                        }
                        for section_id, batch_map in state.lab_completion.items()
                    },
                    diagnostics=diagnostics,
                )
            except GenerationError as exc:
                last_failure = str(exc)
                diagnostics.append(last_failure)

        raise GenerationError(last_failure)

    def _build_lab_demands_for_section(
        self,
        section: Section,
        semester_subjects: list[Subject],
        rng: random.Random,
    ) -> list[LabDemand]:
        lab_subjects = [subject for subject in semester_subjects if subject.subject_type == "Lab"]
        if not lab_subjects:
            return []

        sessions_per_batch = {subject.id: subject.weekly_hours // 2 for subject in lab_subjects}
        patterns = self._build_lab_rotation_patterns(list(sessions_per_batch.keys()), sessions_per_batch, rng)
        return [
            LabDemand(
                demand_id=new_id("labd"),
                section_id=section.id,
                rotation_index=index,
                batch_subject_map=pattern,
            )
            for index, pattern in enumerate(patterns)
        ]

    def _build_lab_rotation_patterns(
        self,
        subject_ids: list[str],
        sessions_per_batch: dict[str, int],
        rng: random.Random,
    ) -> list[dict[str, str]]:
        remaining = {
            batch: {subject_id: sessions_per_batch[subject_id] for subject_id in subject_ids}
            for batch in BATCHES
        }
        plan: list[dict[str, str]] = []
        last_subject_by_batch = {batch: None for batch in BATCHES}
        dead_states: set[tuple[int, ...]] = set()

        def state_key() -> tuple[int, ...]:
            return tuple(remaining[batch][subject_id] for batch in BATCHES for subject_id in subject_ids)

        def candidate_score(mapping: dict[str, str]) -> float:
            score = 0.0
            for batch, subject_id in mapping.items():
                score += remaining[batch][subject_id] * 3
                if last_subject_by_batch[batch] != subject_id:
                    score += 4
                else:
                    score -= 3
            if plan:
                current_pair = tuple(sorted(set(mapping.values())))
                previous_pair = tuple(sorted(set(plan[-1].values())))
                if current_pair != previous_pair:
                    score += 2
            return score + rng.random()

        def backtrack() -> bool:
            if all(value == 0 for batch_map in remaining.values() for value in batch_map.values()):
                return True

            key = state_key()
            if key in dead_states:
                return False

            candidates: list[tuple[float, dict[str, str]]] = []
            for left_subject, right_subject in combinations(subject_ids, 2):
                eligible_left = [batch for batch in BATCHES if remaining[batch][left_subject] > 0]
                if len(eligible_left) < 2:
                    continue
                for left_batches in combinations(eligible_left, 2):
                    right_batches = tuple(batch for batch in BATCHES if batch not in left_batches)
                    if all(remaining[batch][right_subject] > 0 for batch in right_batches):
                        mapping = {
                            left_batches[0]: left_subject,
                            left_batches[1]: left_subject,
                            right_batches[0]: right_subject,
                            right_batches[1]: right_subject,
                        }
                        candidates.append((candidate_score(mapping), mapping))

            if not candidates:
                dead_states.add(key)
                return False

            candidates.sort(key=lambda item: item[0], reverse=True)
            for _, mapping in candidates:
                previous_subjects = {batch: last_subject_by_batch[batch] for batch in BATCHES}
                for batch, subject_id in mapping.items():
                    remaining[batch][subject_id] -= 1
                    last_subject_by_batch[batch] = subject_id
                plan.append(mapping)

                if backtrack():
                    return True

                plan.pop()
                for batch, subject_id in mapping.items():
                    remaining[batch][subject_id] += 1
                    last_subject_by_batch[batch] = previous_subjects[batch]

            dead_states.add(key)
            return False

        if not backtrack():
            raise GenerationError("Could not construct a valid lab rotation plan.")
        return plan

    def _build_theory_demands(
        self,
        sections: list[Section],
        subjects_by_semester: dict[int, list[Subject]],
    ) -> list[TheoryDemand]:
        demands: list[TheoryDemand] = []
        for section in sections:
            theory_subjects = [subject for subject in subjects_by_semester[section.semester] if subject.subject_type == "Theory"]
            remaining = {subject.id: subject.weekly_hours for subject in theory_subjects}
            sequence_no = 1
            while any(value > 0 for value in remaining.values()):
                for subject in sorted(theory_subjects, key=lambda item: (-remaining[item.id], item.name)):
                    if remaining[subject.id] <= 0:
                        continue
                    demands.append(
                        TheoryDemand(
                            demand_id=new_id("theod"),
                            section_id=section.id,
                            subject_id=subject.id,
                            sequence_no=sequence_no,
                        )
                    )
                    remaining[subject.id] -= 1
                    sequence_no += 1
        return demands

    def _schedule_section_labs(
        self,
        section: Section,
        lab_demands: list[LabDemand],
        state: SchedulerState,
        teachers: list[Teacher],
        lab_rooms: list[Room],
        rng: random.Random,
    ) -> bool:
        def recurse(pending: list[LabDemand]) -> bool:
            if not pending:
                return True

            chosen_index = -1
            chosen_candidates: list[LabCandidate] | None = None
            for index, demand in enumerate(pending):
                candidates = self._lab_candidates(demand, state, teachers, lab_rooms, rng)
                if not candidates:
                    return False
                if chosen_candidates is None or len(candidates) < len(chosen_candidates):
                    chosen_index = index
                    chosen_candidates = candidates

            assert chosen_candidates is not None
            demand = pending[chosen_index]
            remaining = pending[:chosen_index] + pending[chosen_index + 1 :]
            for candidate in self._ordered_candidates(chosen_candidates, rng):
                item = state.build_lab_item(
                    demand=demand,
                    day=candidate.day,
                    start_slot=candidate.start_slot,
                    assignments=candidate.assignments,
                    score=candidate.score,
                )
                state.place_item(item)
                if recurse(remaining):
                    return True
                state.remove_item(item.item_id)
            return False

        return recurse(lab_demands)

    def _lab_candidates(
        self,
        demand: LabDemand,
        state: SchedulerState,
        teachers: list[Teacher],
        lab_rooms: list[Room],
        rng: random.Random,
    ) -> list[LabCandidate]:
        candidates: list[LabCandidate] = []
        unique_subjects = tuple(sorted(set(demand.batch_subject_map.values())))

        for day in WEEKDAYS:
            if any(state.section_subject_day_sessions[demand.section_id][subject_id][day] >= 1 for subject_id in unique_subjects):
                continue
            for start_slot, end_slot in LAB_BLOCKS:
                slots = (start_slot, end_slot)
                if not state.section_can_take(demand.section_id, day, slots, MAX_DAILY_SECTION_HOURS):
                    continue

                teacher_assignment = self._find_lab_teacher_assignment(
                    demand=demand,
                    day=day,
                    slots=slots,
                    state=state,
                    teachers=teachers,
                )
                if teacher_assignment is None:
                    continue

                available_rooms = [
                    room.id
                    for room in lab_rooms
                    if state.room_can_take(room.id, day, slots)
                ]
                if len(available_rooms) < len(BATCHES):
                    continue

                available_rooms.sort(key=lambda room_id: self._room_load(state, room_id))
                assignments = []
                for room_id, (batch, subject_id, teacher_id, teacher_score) in zip(available_rooms, teacher_assignment):
                    assignments.append((batch, subject_id, teacher_id, room_id))

                score = sum(item[3] for item in teacher_assignment) + self._section_slot_score(
                    state=state,
                    section_id=demand.section_id,
                    subject_ids=unique_subjects,
                    day=day,
                    slots=slots,
                    is_lab=True,
                )
                score += rng.random()
                candidates.append(LabCandidate(day=day, start_slot=start_slot, assignments=assignments, score=score))

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:14]

    def _find_lab_teacher_assignment(
        self,
        demand: LabDemand,
        day: str,
        slots: tuple[int, ...],
        state: SchedulerState,
        teachers: list[Teacher],
    ) -> list[tuple[str, str, str, float]] | None:
        tasks = [(batch, demand.batch_subject_map[batch]) for batch in BATCHES]
        candidate_map: dict[tuple[str, str], list[tuple[str, float]]] = {}

        for batch, subject_id in tasks:
            teacher_candidates: list[tuple[str, float]] = []
            for teacher in teachers:
                if not state.teacher_can_take(teacher.id, subject_id, day, slots, 2):
                    continue
                score = self._teacher_assignment_score(
                    teacher=teacher,
                    section_id=demand.section_id,
                    subject_id=subject_id,
                    day=day,
                    slots=slots,
                    state=state,
                )
                teacher_candidates.append((teacher.id, score))
            teacher_candidates.sort(key=lambda item: item[1], reverse=True)
            if not teacher_candidates:
                return None
            candidate_map[(batch, subject_id)] = teacher_candidates[:8]

        ordered_tasks = sorted(tasks, key=lambda task: len(candidate_map[task]))
        best_assignment: list[tuple[str, str, str, float]] | None = None
        best_score = float("-inf")

        def search(
            index: int,
            used_teachers: set[str],
            current: list[tuple[str, str, str, float]],
            total_score: float,
        ) -> None:
            nonlocal best_assignment, best_score
            if index >= len(ordered_tasks):
                if total_score > best_score:
                    best_score = total_score
                    best_assignment = current[:]
                return

            batch, subject_id = ordered_tasks[index]
            for teacher_id, score in candidate_map[(batch, subject_id)]:
                if teacher_id in used_teachers:
                    continue
                used_teachers.add(teacher_id)
                current.append((batch, subject_id, teacher_id, score))
                search(index + 1, used_teachers, current, total_score + score)
                current.pop()
                used_teachers.remove(teacher_id)

        search(0, set(), [], 0.0)
        return best_assignment

    def _schedule_theory_demands(
        self,
        demands: list[TheoryDemand],
        state: SchedulerState,
        teachers: list[Teacher],
        classrooms: list[Room],
        rng: random.Random,
    ) -> bool:
        pending = demands[:]
        remaining_for_section: dict[str, int] = defaultdict(int)
        remaining_for_subject: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for demand in pending:
            remaining_for_section[demand.section_id] += 1
            remaining_for_subject[demand.section_id][demand.subject_id] += 1

        while pending:
            focus = sorted(
                pending,
                key=lambda demand: (
                    -remaining_for_section[demand.section_id],
                    -remaining_for_subject[demand.section_id][demand.subject_id],
                    demand.sequence_no,
                ),
            )[:10]

            chosen_demand: TheoryDemand | None = None
            chosen_candidates: list[TheoryCandidate] | None = None
            for demand in focus:
                candidates = self._theory_candidates(demand, state, teachers, classrooms, rng)
                if chosen_candidates is None or len(candidates) < len(chosen_candidates):
                    chosen_demand = demand
                    chosen_candidates = candidates

            if chosen_demand is None or chosen_candidates is None:
                return False

            if not chosen_candidates:
                repaired = self._try_partial_theory_repair(chosen_demand, state, teachers, classrooms, rng)
                if not repaired:
                    return False
                pending.remove(chosen_demand)
                remaining_for_section[chosen_demand.section_id] -= 1
                remaining_for_subject[chosen_demand.section_id][chosen_demand.subject_id] -= 1
                continue

            selected = self._select_best_candidate(chosen_candidates, rng)
            item = state.build_theory_item(
                demand=chosen_demand,
                day=selected.day,
                start_slot=selected.start_slot,
                teacher_id=selected.teacher_id,
                room_id=selected.room_id,
                score=selected.score,
            )
            state.place_item(item)
            pending.remove(chosen_demand)
            remaining_for_section[chosen_demand.section_id] -= 1
            remaining_for_subject[chosen_demand.section_id][chosen_demand.subject_id] -= 1

        return True

    def _theory_candidates(
        self,
        demand: TheoryDemand,
        state: SchedulerState,
        teachers: list[Teacher],
        classrooms: list[Room],
        rng: random.Random,
    ) -> list[TheoryCandidate]:
        candidates: list[TheoryCandidate] = []

        for day in WEEKDAYS:
            if state.section_subject_day_sessions[demand.section_id][demand.subject_id][day] >= 2:
                continue
            for start_slot in range(7):
                slots = (start_slot,)
                if not state.section_can_take(demand.section_id, day, slots, MAX_DAILY_SECTION_HOURS):
                    continue

                available_rooms = [
                    room.id for room in classrooms if state.room_can_take(room.id, day, slots)
                ]
                if not available_rooms:
                    continue
                available_rooms.sort(key=lambda room_id: self._room_load(state, room_id))
                room_id = available_rooms[0]

                section_score = self._section_slot_score(
                    state=state,
                    section_id=demand.section_id,
                    subject_ids=(demand.subject_id,),
                    day=day,
                    slots=slots,
                    is_lab=False,
                )

                for teacher in teachers:
                    if not state.teacher_can_take(teacher.id, demand.subject_id, day, slots, 1):
                        continue
                    score = section_score + self._teacher_assignment_score(
                        teacher=teacher,
                        section_id=demand.section_id,
                        subject_id=demand.subject_id,
                        day=day,
                        slots=slots,
                        state=state,
                    )
                    score += rng.random()
                    candidates.append(
                        TheoryCandidate(
                            day=day,
                            start_slot=start_slot,
                            teacher_id=teacher.id,
                            room_id=room_id,
                            score=score,
                        )
                    )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:24]

    def _try_partial_theory_repair(
        self,
        demand: TheoryDemand,
        state: SchedulerState,
        teachers: list[Teacher],
        classrooms: list[Room],
        rng: random.Random,
    ) -> bool:
        placed = [
            item
            for item in state.placed_items.values()
            if item.kind == "theory" and item.section_id == demand.section_id
        ]
        placed.sort(key=lambda item: item.score)
        candidate_pool = placed[:6]

        for remove_count in (1, 2, 3):
            for subset in combinations(candidate_pool, remove_count):
                removed_items = [state.remove_item(item.item_id) for item in subset]
                bundle = [demand] + [item.demand for item in removed_items if isinstance(item.demand, TheoryDemand)]
                if self._place_theory_bundle(bundle, state, teachers, classrooms, rng):
                    return True
                for item in removed_items:
                    state.place_item(item)
        return False

    def _place_theory_bundle(
        self,
        bundle: list[TheoryDemand],
        state: SchedulerState,
        teachers: list[Teacher],
        classrooms: list[Room],
        rng: random.Random,
    ) -> bool:
        def recurse(pending: list[TheoryDemand]) -> bool:
            if not pending:
                return True

            chosen_demand: TheoryDemand | None = None
            chosen_candidates: list[TheoryCandidate] | None = None
            for demand in pending:
                candidates = self._theory_candidates(demand, state, teachers, classrooms, rng)
                if not candidates:
                    return False
                if chosen_candidates is None or len(candidates) < len(chosen_candidates):
                    chosen_demand = demand
                    chosen_candidates = candidates

            assert chosen_demand is not None
            assert chosen_candidates is not None
            remaining = [item for item in pending if item.demand_id != chosen_demand.demand_id]

            for candidate in self._ordered_candidates(chosen_candidates, rng):
                item = state.build_theory_item(
                    demand=chosen_demand,
                    day=candidate.day,
                    start_slot=candidate.start_slot,
                    teacher_id=candidate.teacher_id,
                    room_id=candidate.room_id,
                    score=candidate.score,
                )
                state.place_item(item)
                if recurse(remaining):
                    return True
                state.remove_item(item.item_id)
            return False

        return recurse(bundle)

    def _teacher_assignment_score(
        self,
        teacher: Teacher,
        section_id: str,
        subject_id: str,
        day: str,
        slots: tuple[int, ...],
        state: SchedulerState,
    ) -> float:
        subject_type = state.lookups.subject_type_by_id[subject_id]
        occupied = state.teacher_busy[teacher.id][day]
        score = 0.0
        score += preferred_subject_score(teacher, subject_id, subject_type)
        score += preferred_slot_score(teacher, slots[0], len(slots))
        score += load_target_improvement(state.teacher_loads[teacher.id], teacher.target_weekly_load, len(slots))
        score += rank_slot_bonus(teacher.rank, slots)
        score += adjacency_bonus(occupied, slots)
        score += state.teacher_section_subject_counts[teacher.id][section_id].get(subject_id, 0) * 8.0
        if subject_id in state.teacher_subjects[teacher.id]:
            score += 6.0
        score -= gap_delta(occupied, slots) * 8.0
        score -= consecutive_penalty(occupied, slots) * 1.2
        score -= last_slot_penalty(slots)
        score -= state.teacher_day_loads[teacher.id][day] * 1.5
        return score

    def _section_slot_score(
        self,
        state: SchedulerState,
        section_id: str,
        subject_ids: Iterable[str],
        day: str,
        slots: tuple[int, ...],
        is_lab: bool,
    ) -> float:
        occupied = state.section_busy[section_id][day]
        score = 0.0
        score += adjacency_bonus(occupied, slots) * 1.2
        score -= gap_delta(occupied, slots) * 12.0
        score -= consecutive_penalty(occupied, slots) * 1.5
        score -= last_slot_penalty(slots) * 1.2
        score -= state.section_day_loads[section_id][day] * 2.0

        for subject_id in subject_ids:
            same_day_sessions = state.section_subject_day_sessions[section_id][subject_id][day]
            if is_lab:
                score -= same_day_sessions * 20.0
            else:
                score -= same_day_sessions * 14.0
            if same_day_sessions == 0:
                spread_bonus = sum(
                    1
                    for other_day in WEEKDAYS
                    if other_day != day and state.section_subject_day_sessions[section_id][subject_id][other_day] > 0
                )
                score += spread_bonus * 3.0
        return score

    def _room_load(self, state: SchedulerState, room_id: str) -> int:
        return sum(len(state.room_busy[room_id][day]) for day in WEEKDAYS)

    def _ordered_candidates(self, candidates: list[TheoryCandidate] | list[LabCandidate], rng: random.Random) -> list:
        if len(candidates) <= 1:
            return candidates
        window = min(4, len(candidates))
        head = candidates[:window]
        tail = candidates[window:]
        rng.shuffle(head)
        head.sort(key=lambda item: item.score, reverse=True)
        return head + tail

    def _select_best_candidate(self, candidates: list[TheoryCandidate], rng: random.Random) -> TheoryCandidate:
        window = min(4, len(candidates))
        return rng.choice(candidates[:window])
