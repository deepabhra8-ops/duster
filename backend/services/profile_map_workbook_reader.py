from pathlib import Path
from typing import IO, Any, Mapping

import polars as pl

from utils.logger import get_logger

logger = get_logger(__name__)

_EXCEL_ENGINES = ("calamine", "openpyxl")


def _read_all_sheets(source: Any) -> dict[str, pl.DataFrame]:
    last_error: Exception | None = None

    for engine in _EXCEL_ENGINES:
        if hasattr(source, "seek"):
            source.seek(0)

        try:
            return pl.read_excel(
                source, sheet_id=0, infer_schema_length=0, engine=engine
            )
        except (ImportError, OSError) as exc:
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
    def inspect(self, source: str | Path | IO[bytes]) -> dict[str, Any]:
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
        rows = list(frame.iter_rows(named=True))

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
        normalized = rules_text.replace(",", "|").replace(";", "|")

        return [part.strip().upper() for part in normalized.split("|") if part.strip()]

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    @classmethod
    def _first_present(cls, row: Mapping[str, Any], candidates: list[str]) -> str:
        for candidate in candidates:
            if candidate in row:
                text = cls._text(row[candidate])

                if text:
                    return text

        return ""


profile_map_workbook_reader = ProfileMapWorkbookReader()
