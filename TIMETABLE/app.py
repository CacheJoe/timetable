from __future__ import annotations

from pathlib import Path

import streamlit as st

from timetable.storage import JsonRepository
from timetable.ui import render_app


ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Timetable Management System",
    layout="wide",
)


def main() -> None:
    repo = JsonRepository(ROOT)
    render_app(repo, ROOT)


if __name__ == "__main__":
    main()
