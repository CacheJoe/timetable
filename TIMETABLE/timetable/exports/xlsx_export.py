from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from timetable.reporting import build_lab_completion_rows, build_section_tables, build_teacher_load_rows, build_teacher_tables, rows_to_matrix


def _sheet_name(name: str, used: set[str]) -> str:
    base = "".join(char for char in name if char not in '[]:*?/\\')[:31] or "Sheet"
    candidate = base
    counter = 1
    while candidate in used:
        suffix = f"_{counter}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def _column_name(index: int) -> str:
    label = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _sheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{_column_name(column_index)}{row_index}"
            text = escape(value).replace("\n", "&#10;")
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def workbook_bytes(sheets: list[tuple[str, list[list[str]]]]) -> bytes:
    used_names: set[str] = set()
    normalized = [(_sheet_name(name, used_names), rows) for name, rows in sheets]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for index in range(1, len(normalized) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
                for index, (name, _) in enumerate(normalized, start=1)
            )
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(normalized) + 1)
            )
            + "</Relationships>",
        )
        for index, (_, rows) in enumerate(normalized, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))
    return output.getvalue()


def section_workbook_bytes(app_state) -> bytes:
    tables = build_section_tables(app_state)
    sheets = [(name, rows_to_matrix(rows)) for name, rows in tables.items()]
    sheets.append(("Teacher Loads", rows_to_matrix(build_teacher_load_rows(app_state))))
    sheets.append(("Lab Completion", rows_to_matrix(build_lab_completion_rows(app_state))))
    return workbook_bytes(sheets)


def teacher_workbook_bytes(app_state) -> bytes:
    tables = build_teacher_tables(app_state)
    sheets = [(name, rows_to_matrix(rows)) for name, rows in tables.items()]
    sheets.append(("Teacher Loads", rows_to_matrix(build_teacher_load_rows(app_state))))
    return workbook_bytes(sheets)
