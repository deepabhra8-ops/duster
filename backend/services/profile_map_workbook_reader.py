"""Reads a profile map workbook independently of the PySpark engine context.

Used by the web layer to inspect uploaded mapping workbooks before converting
them into draft jobs, extracting table/column schemas and validations without
touching engine.core types.

Reads with polars (calamine). Two things that matters for correctness, beyond
speed: every cell is read as text, so a column of codes like "00123" keeps its
leading zeros instead of arriving as the number 123; and an empty cell is None
rather than a float NaN, so a missed guard can no longer put the literal string
"nan" into a profile map.
"""

from pathlib import Path
from typing import IO, Any, Mapping

import polars as pl

from utils.logger import get_logger

logger = get_logger(__name__)

# polars' default Excel engine is calamine, which is a compiled Rust extension
# (fastexcel). On a locked-down Windows host that .pyd can be blocked outright -
# "DLL load failed while importing lib: An Application Control policy has blocked
# this file" - and the import fails before any workbook is touched. openpyxl is
# pure Python, is already a declared dependency, and reads the same file, so it
# is the fallback rather than an error the user can do nothing about.
#
# Ordered deliberately: calamine first because it releases the GIL and is several
# times faster on a multi-sheet profile map, openpyxl only when calamine cannot
# load at all.
_EXCEL_ENGINES = ("calamine", "openpyxl")


def _read_all_sheets(source: Any) -> dict[str, pl.DataFrame]:
    """Read every sheet as text, whichever Excel engine this host can load.

    sheet_id=0 reads every sheet in one pass; infer_schema_length=0 keeps every
    value as text (see the module docstring).
    """
    last_error: Exception | None = None

    for engine in _EXCEL_ENGINES:
        # A stream is consumed by a failed attempt, so rewind before retrying -
        # otherwise the fallback reads zero bytes and reports a corrupt file.
        if hasattr(source, "seek"):
            source.seek(0)

        try:
            return pl.read_excel(
                source, sheet_id=0, infer_schema_length=0, engine=engine
            )
        except (ImportError, OSError) as exc:
            # The engine itself is unavailable - a blocked or missing native
            # module - rather than the workbook being unreadable. Try the next.
            logger.warning("Excel engine '%s' unavailable: %s", engine, exc)
            last_error = exc

    raise RuntimeError(
        "No usable Excel engine: "
        + ", ".join(_EXCEL_ENGINES)
        + f". Last error: {last_error}"
    )



COLUMN_HEADER_CANDIDATES = ["Column", "Column Name"]
CDE_HEADER_CANDIDATES = ["CDE\n(X=Yes)", "CDE (X=Yes)", "CDE"]
RULES_HEADER_CANDIDATES = [
    "Applicable Rule\n(Single ID)",
    "Applicable Rules\n(comma-sep IDs)",
    "Applicable Rules",
]
PARAMETERS_HEADER_CANDIDATES = [
    "Rule Parameters\n(see Instructions)",
    "Rule Parameters",
]

_TRUTHY_CDE = {"X", "Y", "YES", "TRUE", "1"}


class ProfileMapWorkbookReader:
    """Reads a profile map workbook for inspection."""

    def inspect(self, source: str | Path | IO[bytes]) -> dict[str, Any]:
        """Read tables and columns from a workbook given as a path or an open byte stream.

        A byte stream is the normal case for an upload: when S3 is configured the file
        is never written to this container's disk, so there is no path to read back.
        polars' read_excel accepts either, so the only thing that has to vary is
        whether the source is turned into a Path first.
        """
        label = source if isinstance(source, (str, Path)) else "<uploaded workbook>"

        if isinstance(source, (str, Path)):
            source = Path(source)

        try:
            sheets = _read_all_sheets(source)
            tables = []

            for sheet_name, frame in sheets.items():
                if sheet_name.lower() == "instructions":
                    continue

                if frame.is_empty():
                    continue

                frame = frame.rename(
                    {name: str(name).strip() for name in frame.columns}
                )

                table = self._read_sheet(sheet_name=sheet_name, frame=frame)

                if table is not None:
                    tables.append(table)

            return {"tables": tables}

        except Exception as exc:
            logger.exception("Failed to inspect profile map workbook %s", label)
            raise ValueError(f"Could not read workbook: {exc}")

    def _read_sheet(self, sheet_name: str, frame: pl.DataFrame) -> dict[str, Any] | None:
        """Turn one sheet into a table entry, or None if it holds no columns."""
        rows = list(frame.iter_rows(named=True))

        # The sheet name is a fallback; a "Table" column names the real table.
        table_name = sheet_name

        if "Table" in frame.columns and rows:
            first_value = self._text(rows[0].get("Table"))

            if first_value:
                table_name = first_value

        columns = [
            column
            for column in (self._read_row(row) for row in rows)
            if column is not None
        ]

        if not columns:
            return None

        return {"table_name": table_name, "columns": columns}

    def _read_row(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        """Turn one spreadsheet row into a column definition, or None if unnamed."""
        column_name = self._first_present(row, COLUMN_HEADER_CANDIDATES)

        if not column_name:
            return None

        rules_text = self._first_present(row, RULES_HEADER_CANDIDATES)

        return {
            "column_name": column_name,
            "data_type": self._text(row.get("Data Type")),
            "cde": self._first_present(row, CDE_HEADER_CANDIDATES).upper() in _TRUTHY_CDE,
            "rule_ids": self._split_rule_ids(rules_text),
            "parameters": self._first_present(row, PARAMETERS_HEADER_CANDIDATES),
            "analyst_notes": self._text(row.get("Analyst Notes")),
        }

    @staticmethod
    def _split_rule_ids(rules_text: str) -> list[str]:
        """Split a rules cell on any of the separators analysts actually use."""
        normalized = rules_text.replace(",", "|").replace(";", "|")

        return [part.strip().upper() for part in normalized.split("|") if part.strip()]

    @staticmethod
    def _text(value: Any) -> str:
        """Stringify a cell, treating a missing value as empty rather than 'None'."""
        if value is None:
            return ""

        return str(value).strip()

    @classmethod
    def _first_present(cls, row: Mapping[str, Any], candidates: list[str]) -> str:
        """Return the first candidate header that this row actually carries a value for.

        Header spellings have changed over time and old workbooks are still
        uploaded, so each field accepts several.
        """
        for candidate in candidates:
            if candidate in row:
                text = cls._text(row[candidate])

                if text:
                    return text

        return ""


profile_map_workbook_reader = ProfileMapWorkbookReader()
