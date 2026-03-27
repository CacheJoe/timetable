from __future__ import annotations

from collections import defaultdict

from timetable.exports.csv_export import section_csv_zip_bytes, teacher_csv_zip_bytes
from timetable.exports.xlsx_export import section_workbook_bytes, teacher_workbook_bytes
from timetable.sample_data import build_demo_state
from timetable.scheduling.generator import TimetableGenerator


def main() -> None:
    state = build_demo_state()
    result = TimetableGenerator().generate(state, max_attempts=12, seed=1234)
    state.generated_timetable = result

    teacher_slots: dict[str, set[tuple[str, int]]] = defaultdict(set)
    room_slots: dict[str, set[tuple[str, int]]] = defaultdict(set)
    section_slots: dict[str, set[tuple[str, int]]] = defaultdict(set)

    for entry in result.entries:
        for slot in range(entry.start_slot, entry.start_slot + entry.duration):
            teacher_key = (entry.day, slot)
            room_key = (entry.day, slot)
            section_key = (entry.day, slot)
            assert teacher_key not in teacher_slots[entry.teacher_id], f"Teacher overlap detected for {entry.teacher_id}"
            assert room_key not in room_slots[entry.room_id], f"Room overlap detected for {entry.room_id}"
            if entry.entry_type == "Theory":
                assert section_key not in section_slots[entry.section_id], f"Section overlap detected for {entry.section_id}"
            section_slots[entry.section_id].add(section_key)
            teacher_slots[entry.teacher_id].add(teacher_key)
            room_slots[entry.room_id].add(room_key)

    assert section_workbook_bytes(state), "Section workbook export failed."
    assert teacher_workbook_bytes(state), "Teacher workbook export failed."
    assert section_csv_zip_bytes(state), "Section CSV export failed."
    assert teacher_csv_zip_bytes(state), "Teacher CSV export failed."

    print("Smoke test passed.")
    print(f"Entries: {len(result.entries)}")
    print(f"Soft score: {result.total_soft_score}")
    print(f"Attempts: {result.attempt_count}")


if __name__ == "__main__":
    main()
