# Timetable Management System

A production-oriented timetable management system for a single academic branch, built with Python and Streamlit.

## Features

- Persistent CRUD management for teachers, subjects, sections, and rooms
- Constraint-aware timetable generation with:
  - hard validation
  - soft-score optimization
  - parallel lab execution
  - batch-wise lab rotation tracking
  - teacher workload balancing
  - retry and partial reshuffle strategies
- Section-wise and teacher-wise timetable views
- Excel and CSV exports without requiring pandas

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Notes

- Sections automatically use all subjects defined for their semester.
- Labs require at least four lab rooms and four teachers because each batch is scheduled independently during a lab block.
- Lab weekly hours must be even because labs are scheduled in 2-hour blocks.
