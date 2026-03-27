from __future__ import annotations

from timetable.constants import TEACHING_SLOT_LABELS
from timetable.models import AppState, Room, Section, Subject, Teacher, new_id


def build_demo_state() -> AppState:
    subjects = [
        Subject(id=new_id("sub"), name="Data Structures", subject_type="Theory", semester=3, weekly_hours=3),
        Subject(id=new_id("sub"), name="Discrete Mathematics", subject_type="Theory", semester=3, weekly_hours=3),
        Subject(id=new_id("sub"), name="Digital Logic", subject_type="Theory", semester=3, weekly_hours=3),
        Subject(id=new_id("sub"), name="Python Programming", subject_type="Theory", semester=3, weekly_hours=3),
        Subject(id=new_id("sub"), name="Programming Lab", subject_type="Lab", semester=3, weekly_hours=2),
        Subject(id=new_id("sub"), name="Digital Systems Lab", subject_type="Lab", semester=3, weekly_hours=2),
        Subject(id=new_id("sub"), name="Data Structures Lab", subject_type="Lab", semester=3, weekly_hours=2),
        Subject(id=new_id("sub"), name="Operating Systems", subject_type="Theory", semester=5, weekly_hours=3),
        Subject(id=new_id("sub"), name="Database Systems", subject_type="Theory", semester=5, weekly_hours=3),
        Subject(id=new_id("sub"), name="Computer Networks", subject_type="Theory", semester=5, weekly_hours=3),
        Subject(id=new_id("sub"), name="Web Technologies", subject_type="Theory", semester=5, weekly_hours=2),
        Subject(id=new_id("sub"), name="Database Lab", subject_type="Lab", semester=5, weekly_hours=2),
        Subject(id=new_id("sub"), name="Networks Lab", subject_type="Lab", semester=5, weekly_hours=2),
        Subject(id=new_id("sub"), name="Web Lab", subject_type="Lab", semester=5, weekly_hours=2),
    ]

    subject_by_name = {subject.name: subject.id for subject in subjects}

    teachers = [
        Teacher(
            id=new_id("teach"),
            name="Dr. Mehta",
            rank="Professor",
            max_weekly_load=14,
            target_weekly_load=10,
            max_subjects=2,
            preferred_theory_subject_ids=[subject_by_name["Operating Systems"], subject_by_name["Database Systems"]],
            preferred_lab_subject_ids=[subject_by_name["Database Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[1], TEACHING_SLOT_LABELS[2], TEACHING_SLOT_LABELS[4]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Kulkarni",
            rank="Associate Professor",
            max_weekly_load=16,
            target_weekly_load=12,
            max_subjects=3,
            preferred_theory_subject_ids=[subject_by_name["Data Structures"], subject_by_name["Discrete Mathematics"]],
            preferred_lab_subject_ids=[subject_by_name["Data Structures Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[0], TEACHING_SLOT_LABELS[1], TEACHING_SLOT_LABELS[2]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Sharma",
            rank="Assistant Professor",
            max_weekly_load=18,
            target_weekly_load=14,
            max_subjects=3,
            preferred_theory_subject_ids=[subject_by_name["Computer Networks"], subject_by_name["Digital Logic"]],
            preferred_lab_subject_ids=[subject_by_name["Networks Lab"], subject_by_name["Digital Systems Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[2], TEACHING_SLOT_LABELS[3], TEACHING_SLOT_LABELS[4]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Iyer",
            rank="Assistant Professor",
            max_weekly_load=18,
            target_weekly_load=14,
            max_subjects=3,
            preferred_theory_subject_ids=[subject_by_name["Python Programming"], subject_by_name["Web Technologies"]],
            preferred_lab_subject_ids=[subject_by_name["Programming Lab"], subject_by_name["Web Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[0], TEACHING_SLOT_LABELS[1], TEACHING_SLOT_LABELS[4]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Patil",
            rank="Associate Professor",
            max_weekly_load=16,
            target_weekly_load=12,
            max_subjects=3,
            preferred_theory_subject_ids=[subject_by_name["Database Systems"], subject_by_name["Discrete Mathematics"]],
            preferred_lab_subject_ids=[subject_by_name["Database Lab"], subject_by_name["Programming Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[1], TEACHING_SLOT_LABELS[2], TEACHING_SLOT_LABELS[5]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Deshmukh",
            rank="Assistant Professor",
            max_weekly_load=18,
            target_weekly_load=14,
            max_subjects=4,
            preferred_theory_subject_ids=[subject_by_name["Operating Systems"], subject_by_name["Digital Logic"]],
            preferred_lab_subject_ids=[subject_by_name["Networks Lab"], subject_by_name["Data Structures Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[0], TEACHING_SLOT_LABELS[4], TEACHING_SLOT_LABELS[5]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Rao",
            rank="Visiting Faculty",
            max_weekly_load=10,
            target_weekly_load=8,
            max_subjects=2,
            preferred_theory_subject_ids=[subject_by_name["Web Technologies"], subject_by_name["Python Programming"]],
            preferred_lab_subject_ids=[subject_by_name["Web Lab"], subject_by_name["Programming Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[4], TEACHING_SLOT_LABELS[5]],
        ),
        Teacher(
            id=new_id("teach"),
            name="Prof. Nair",
            rank="Assistant Professor",
            max_weekly_load=18,
            target_weekly_load=14,
            max_subjects=3,
            preferred_theory_subject_ids=[subject_by_name["Computer Networks"], subject_by_name["Data Structures"]],
            preferred_lab_subject_ids=[subject_by_name["Networks Lab"], subject_by_name["Digital Systems Lab"]],
            preferred_slots=[TEACHING_SLOT_LABELS[1], TEACHING_SLOT_LABELS[2], TEACHING_SLOT_LABELS[4]],
        ),
    ]

    sections = [
        Section(id=new_id("sec"), name="CSE-3A", semester=3),
        Section(id=new_id("sec"), name="CSE-5A", semester=5),
    ]

    rooms = [
        Room(id=new_id("room"), name="CR-301", room_type="Classroom"),
        Room(id=new_id("room"), name="CR-302", room_type="Classroom"),
        Room(id=new_id("room"), name="LAB-1", room_type="Lab"),
        Room(id=new_id("room"), name="LAB-2", room_type="Lab"),
        Room(id=new_id("room"), name="LAB-3", room_type="Lab"),
        Room(id=new_id("room"), name="LAB-4", room_type="Lab"),
        Room(id=new_id("room"), name="LAB-5", room_type="Lab"),
    ]

    for subject in subjects:
        subject.validate()
    subject_type_by_id = {subject.id: subject.subject_type for subject in subjects}
    for teacher in teachers:
        teacher.validate(subject_type_by_id)
    for section in sections:
        section.validate()
    for room in rooms:
        room.validate()

    return AppState(version=1, teachers=teachers, subjects=subjects, sections=sections, rooms=rooms, generated_timetable=None)
