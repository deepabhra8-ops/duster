"""Renders stored profile-map rows to a formatted .xlsx workbook.

Deliberately does not use engine.profile_map.ProfileMapWriter: the web container
ships without the engine package (Dockerfile stage 2 copies only config/,
repositories/, routes/, services/, utils/), so that class isn't importable here.
xlsxwriter is already a dependency via the existing requirements.

Export happens on demand rather than at run time, which is what makes a downloaded
workbook reflect the analyst's edits instead of the raw profiling output.
"""

from __future__ import annotations

import io
from typing import Any

import xlsxwriter

from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger


logger = get_logger(__name__)


# Column order of the generated sheet. Mirrors the engine's ProfileMapWriter.COLUMNS
# so an exported workbook is interchangeable with a Glue-generated one - the
# validator's .xlsx upload path has to be able to read either.
COLUMNS = (
    "Row ID",
    "Enabled",
    "Table",
    "Column",
    "Data Type",
    "Total Count",
    "Null Count",
    "Null %",
    "Distinct Count",
    "Unique %",
    "Min Value",
    "Max Value",
    "CDE (X=Yes)",
    "Applicable Rule\n(Single ID)",
    "Rule Parameters",
    "Analyst Notes",
)

# The exported header text (above) has to match the engine's ProfileMapWriter
# so a re-uploaded workbook is readable by the validator, but the stored rows
# (from profile_map_service) key applicable-rule values as plain "Applicable
# Rules" - map the display header to the row key it actually reads from.
_COLUMN_TO_ROW_KEY = {
    "Applicable Rule\n(Single ID)": "Applicable Rules",
}

_MAX_SHEET_NAME = 31
_MAX_COLUMN_WIDTH = 50
_INVALID_SHEET_CHARS = ("[", "]", ":", "*", "?", "/", "\\")


class ProfileMapExporter:
    """Builds a profile-map workbook from JSON rows."""

    def build(self, rows: list[dict[str, Any]]) -> bytes:
        """Return the .xlsx bytes for these rows, one sheet per source table."""
        buffer = io.BytesIO()
        
        # Filter out disabled rows
        enabled_rows = [
            row for row in rows 
            if str(row.get("Enabled", "Y")).strip().upper() == "Y"
        ]

        workbook = xlsxwriter.Workbook(
            buffer,
            {**XLSXWRITER_SAFE_OPTIONS, "in_memory": True},
        )

        try:
            header_format = workbook.add_format(
                {"bold": True, "border": 1, "align": "center", "valign": "vcenter"}
            )
            cell_format = workbook.add_format({"border": 1})

            used_sheet_names: set[str] = set()

            for table_name, table_rows in self._group_by_table(enabled_rows).items():
                self._write_sheet(
                    workbook=workbook,
                    sheet_name=self._safe_sheet_name(table_name, used_sheet_names),
                    rows=table_rows,
                    header_format=header_format,
                    cell_format=cell_format,
                )

            if not enabled_rows:
                # xlsxwriter refuses to save a workbook with no sheets.
                workbook.add_worksheet("Profile Map")
        finally:
            workbook.close()

        logger.info("Built profile-map workbook with %s rows", len(rows))
        return buffer.getvalue()

    @staticmethod
    def _group_by_table(
        rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group rows by their Table value, preserving first-seen order."""
        grouped: dict[str, list[dict[str, Any]]] = {}

        for row in rows:
            table = str(row.get("Table", "") or "Table").strip() or "Table"
            grouped.setdefault(table, []).append(row)

        return grouped

    def _write_sheet(
        self,
        workbook: Any,
        sheet_name: str,
        rows: list[dict[str, Any]],
        header_format: Any,
        cell_format: Any,
    ) -> None:
        """Write one table's rows as a formatted, filterable sheet."""
        worksheet = workbook.add_worksheet(sheet_name)

        widths = [len(column) + 2 for column in COLUMNS]

        for index, column in enumerate(COLUMNS):
            worksheet.write(0, index, column, header_format)

        for row_index, row in enumerate(rows, start=1):
            for column_index, column in enumerate(COLUMNS):
                row_key = _COLUMN_TO_ROW_KEY.get(column, column)
                value = row.get(row_key, "")
                value = "" if value is None else str(value)

                worksheet.write(row_index, column_index, value, cell_format)
                widths[column_index] = max(widths[column_index], len(value) + 2)

        for index, width in enumerate(widths):
            worksheet.set_column(index, index, min(width, _MAX_COLUMN_WIDTH))

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(len(rows), 1), len(COLUMNS) - 1)

    @staticmethod
    def _safe_sheet_name(table_name: str, used: set[str] | None = None) -> str:
        """Sanitize a table name into a valid, length-limited, unique Excel sheet name.

        Uniqueness is not cosmetic. Two distinct tables whose names share their
        first 31 characters - "Customer_Account_Master_Record_Alpha" and
        "..._Beta" - both truncate to "Customer_Account_Master_Record_", and
        xlsxwriter raises DuplicateWorksheetName, which failed the entire export
        rather than just that sheet. Mirrors ProfileMapWriter._safe_sheet_name,
        which already deduplicates this way.

        The suffix does not lose information: the untruncated table name is also
        written into each row's "Table" column, and that is what both readers key
        the profile map by.
        """
        sheet_name = str(table_name).strip()

        for character in _INVALID_SHEET_CHARS:
            sheet_name = sheet_name.replace(character, "_")

        base_name = sheet_name or "Table"
        proposed = base_name[:_MAX_SHEET_NAME]

        if used is None:
            return proposed

        suffix = 1
        lowered = {name.lower() for name in used}

        while proposed.lower() in lowered:
            suffix_text = f"_{suffix}"
            proposed = base_name[: _MAX_SHEET_NAME - len(suffix_text)] + suffix_text
            suffix += 1

        used.add(proposed)

        return proposed


profile_map_exporter = ProfileMapExporter()
