from __future__ import annotations

import csv
import io
import zipfile

from timetable.reporting import build_room_tables, build_section_tables, build_teacher_tables, rows_to_matrix


def csv_zip_bytes(tables: dict[str, list[dict[str, str]]], prefix: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, rows in tables.items():
            matrix = rows_to_matrix(rows)
            stream = io.StringIO()
            writer = csv.writer(stream)
            for row in matrix:
                writer.writerow(row)
            safe_name = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in name)
            archive.writestr(f"{prefix}_{safe_name}.csv", stream.getvalue())
    return output.getvalue()


def section_csv_zip_bytes(app_state) -> bytes:
    return csv_zip_bytes(build_section_tables(app_state), "section")


def teacher_csv_zip_bytes(app_state) -> bytes:
    return csv_zip_bytes(build_teacher_tables(app_state), "teacher")


def room_csv_zip_bytes(app_state) -> bytes:
    return csv_zip_bytes(build_room_tables(app_state), "room")
