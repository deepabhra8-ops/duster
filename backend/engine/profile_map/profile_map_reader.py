"""Reads a profile map workbook (current or legacy header format) back into TableRuleConfiguration objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import polars as pl

from engine.core.result_models import (
    RuleConfiguration,
    TableRuleConfiguration,
)
from utils.logger import get_logger


logger = get_logger(__name__)


COLUMN_HEADER_CANDIDATES = ["Column", "Column Name"]
# "CDE (X=Yes)" is the stored-JSON spelling (profile_map_rows.build_rows); the
# newline form is what ProfileMapWriter puts in a worksheet header. Both must be
# accepted, since a validator run can source its map from either.
CDE_HEADER_CANDIDATES = ["CDE\n(X=Yes)", "CDE (X=Yes)", "CDE"]
RULES_HEADER_CANDIDATES = [
    # The spelling ProfileMapWriter AND services/profile_map_exporter.py both
    # write. Its absence here is what made an uploaded workbook validate nothing:
    # every column parsed with no rule ids, so the run completed "successfully"
    # against zero checks and produced an empty report and an empty workbook.
    #
    # from_rows() was unaffected because profile_map_rows keys that field as
    # plain "Applicable Rules", which was already listed - which is exactly why
    # a validator sourced from a Profile Mapper job worked while the uploaded
    # workbook came back empty.
    "Applicable Rule\n(Single ID)",
    "Applicable Rules\n(comma-sep IDs)",
    "Applicable Rules",
]
PARAMETERS_HEADER_CANDIDATES = [
    "Rule Parameters\n(see Instructions)",
    "Rule Parameters",
]

METADATA_EXCLUDED_HEADERS = {
    *COLUMN_HEADER_CANDIDATES,
    *CDE_HEADER_CANDIDATES,
    *RULES_HEADER_CANDIDATES,
    *PARAMETERS_HEADER_CANDIDATES,
    "Analyst Notes",
}


class ProfileMapReader:
    """Reads a profile map produced by ProfileMapWriter, accepting both current and legacy headers."""

    def read(
        self,
        path: str | Path,
    ) -> dict[str, TableRuleConfiguration]:
        """Read every table sheet in a profile map workbook."""
        path = Path(path)

        try:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Profile map not found: {path}"
                )

            # One call reads every sheet; calamine parses them in Rust, so
            # there is no per-sheet Python loop worth parallelising here.
            # infer_schema_length=0 keeps every cell as text, so codes like
            # "00123" keep their leading zeros instead of arriving as numbers.
            sheets = pl.read_excel(path, sheet_id=0, infer_schema_length=0)
            result: dict[str, TableRuleConfiguration] = {}

            for sheet_name, frame in sheets.items():
                if sheet_name.strip().lower() == "instructions":
                    continue

                if frame.is_empty():
                    continue

                rows = self._frame_rows(frame)

                table_config = self._read_table(
                    table_name=self._table_name_for(sheet_name, rows),
                    rows=rows,
                )
                result[table_config.table_name] = table_config

            logger.info(
                "Read profile map '%s' with %s table configurations",
                path,
                len(result),
            )
            return result
        except Exception:
            logger.exception("Failed to read profile map '%s'", path)
            raise

    @staticmethod
    def _table_name_for(
        sheet_name: str,
        rows: list[Mapping[str, Any]],
    ) -> str:
        """Return the real source table name for a sheet.

        The sheet name is only a fallback. Excel caps a worksheet name at 31
        characters and forbids []:*?/\\, so both writers sanitize and truncate -
        and ProfileMapWriter additionally appends _1, _2 ... to keep names unique.
        A table called "Account_Contact_Relationship_History__c" therefore lives on
        a sheet called "Account_Contact_Relationship_Hi".

        Keying the profile map by that truncated name was a silent correctness bug
        on multi-table runs: validation_engine looks its tables up by the name in
        the job config (the real one), found no entry, and skipped the table -
        producing a "successful" run that validated nothing for it. The "Table"
        column carries the untruncated name, which is what from_rows() already
        groups by, so reading it here makes the workbook and stored-rows paths
        agree.
        """
        for row in rows:
            table_name = str(row.get("Table", "") or "").strip()

            if table_name:
                return table_name

        return sheet_name

    def from_rows(
        self,
        rows: list[Mapping[str, Any]],
    ) -> dict[str, TableRuleConfiguration]:
        """Build table configurations from stored JSON profile-map rows.

        The rows are the same shape profile_map_rows.build_rows() produces and the
        API stores, so a validator run can consume an analyst's in-browser edits
        directly instead of round-tripping them through a workbook. Rows are grouped
        by their "Table" value; each group becomes one TableRuleConfiguration.

        Header parsing is shared with the Excel path via _read_table(), so both
        sources accept the same current and legacy header spellings.
        """
        try:
            grouped: dict[str, list[Mapping[str, Any]]] = {}

            for row in rows:
                table_name = str(row.get("Table", "") or "").strip()

                if not table_name:
                    continue

                grouped.setdefault(table_name, []).append(row)

            result: dict[str, TableRuleConfiguration] = {}

            for table_name, table_rows in grouped.items():
                # The rows are already dicts; they used to be packed into a
                # DataFrame purely so _read_table could iterate them straight
                # back out again.
                result[table_name] = self._read_table(
                    table_name=table_name,
                    rows=list(table_rows),
                )

            logger.info(
                "Built profile map from %s stored rows across %s table(s)",
                len(rows),
                len(result),
            )
            return result
        except Exception:
            logger.exception("Failed to build profile map from stored rows")
            raise

    def read_table(
        self,
        path: str | Path,
        table_name: str,
    ) -> TableRuleConfiguration:
        """Read one table sheet from a profile map workbook."""
        path = Path(path)

        try:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Profile map not found: {path}"
                )

            frame = pl.read_excel(
                path,
                sheet_name=table_name,
                infer_schema_length=0,
            )

            result = self._read_table(
                table_name=table_name,
                rows=self._frame_rows(frame),
            )
            logger.info(
                "Read profile-map table '%s' from '%s'",
                table_name,
                path,
            )
            return result
        except Exception:
            logger.exception(
                "Failed to read profile-map table '%s' from '%s'",
                table_name,
                path,
            )
            raise

    def _read_table(
        self,
        table_name: str,
        rows: list[Mapping[str, Any]],
    ) -> TableRuleConfiguration:
        """Parse a table's rows into a TableRuleConfiguration.

        Takes plain row mappings rather than a dataframe so both sources feed it
        directly: a workbook sheet's rows, and the stored JSON rows the API
        hands the validator, which are already in this shape.
        """
        try:
            rows = [self._normalize_keys(row) for row in rows]

            actual_table_name = table_name

            if rows:
                first_value = self._clean_text(rows[0].get("Table"))

                if first_value:
                    actual_table_name = first_value

            columns: list[RuleConfiguration] = []

            for row in rows:
                column_name = self._get_value_any(
                    row,
                    COLUMN_HEADER_CANDIDATES,
                )

                if not column_name:
                    continue

                rule_ids = self._parse_rule_ids(
                    self._get_value_any(
                        row,
                        RULES_HEADER_CANDIDATES,
                    )
                )

                parameters = self._get_value_any(
                    row,
                    PARAMETERS_HEADER_CANDIDATES,
                )

                cde = self._parse_bool(
                    self._get_value_any(
                        row,
                        CDE_HEADER_CANDIDATES,
                    )
                )

                analyst_notes = self._get_value(
                    row,
                    "Analyst Notes",
                )

                metadata = {
                    key: self._clean_value(value)
                    for key, value in row.items()
                    if key not in METADATA_EXCLUDED_HEADERS
                }

                columns.append(
                    RuleConfiguration(
                        column_name=column_name,
                        rule_ids=tuple(rule_ids),
                        parameters=parameters,
                        cde=cde,
                        analyst_notes=analyst_notes,
                        metadata=metadata,
                    )
                )

            return TableRuleConfiguration(
                table_name=actual_table_name,
                columns=tuple(columns),
            )
        except Exception:
            logger.exception(
                "Failed to parse profile-map table '%s'",
                table_name,
            )
            raise

    @staticmethod
    def _frame_rows(frame: "pl.DataFrame") -> list[Mapping[str, Any]]:
        """Turn a sheet into row mappings."""
        return list(frame.iter_rows(named=True))

    @staticmethod
    def _normalize_keys(
        row: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Strip whitespace from a row's header keys."""
        return {str(key).strip(): value for key, value in row.items()}

    @staticmethod
    def _is_missing(value: Any) -> bool:
        """Whether a cell holds no value.

        Covers None (what polars and stored JSON rows use) and NaN (which can
        still arrive from a numeric source), without needing a dataframe
        library's own null check.
        """
        if value is None:
            return True

        return isinstance(value, float) and value != value

    @classmethod
    def _clean_text(cls, value: Any, default: str = "") -> str:
        """Stringify a cell, returning the default when it holds no value."""
        if cls._is_missing(value):
            return default

        return str(value).strip()

    @classmethod
    def _get_value(
        cls,
        row: Mapping[str, Any],
        column_name: str,
        default: str = "",
    ) -> str:
        """Return a stripped string value for one column, or a default."""
        if column_name not in row:
            return default

        return cls._clean_text(row[column_name], default)

    @classmethod
    def _get_value_any(
        cls,
        row: Mapping[str, Any],
        candidate_columns: list[str],
        default: str = "",
    ) -> str:
        """Return a stripped string value from the first matching candidate column."""
        for column_name in candidate_columns:
            if column_name in row:
                value = row[column_name]

                if not cls._is_missing(value):
                    return str(value).strip()

        return default

    @staticmethod
    def _parse_rule_ids(
        value: str,
    ) -> list[str]:
        """Parse a comma/semicolon/pipe-separated rule ID string into a list."""
        if not value:
            return []

        normalized = (
            value
            .replace(",", "|")
            .replace(";", "|")
        )

        return [
            rule.strip().upper()
            for rule in normalized.split("|")
            if rule.strip()
        ]

    @staticmethod
    def _parse_bool(
        value: str,
    ) -> bool:
        """Parse a CDE cell value as a boolean."""
        return value.strip().lower() in {
            "true",
            "yes",
            "y",
            "1",
            "x",
        }

    @classmethod
    def _clean_value(
        cls,
        value: Any,
    ) -> Any:
        """Replace a missing value with an empty string; pass others through unchanged."""
        if cls._is_missing(value):
            return ""

        return value
