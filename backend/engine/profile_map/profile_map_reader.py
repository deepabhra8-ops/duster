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

METADATA_EXCLUDED_HEADERS = {
    *COLUMN_HEADER_CANDIDATES,
    *CDE_HEADER_CANDIDATES,
    *RULES_HEADER_CANDIDATES,
    *PARAMETERS_HEADER_CANDIDATES,
    "Analyst Notes",
}


class ProfileMapReader:
    def read(
        self,
        path: str | Path,
    ) -> dict[str, TableRuleConfiguration]:
        path = Path(path)

        try:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Profile map not found: {path}"
                )

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
        for row in rows:
            table_name = str(row.get("Table", "") or "").strip()

            if table_name:
                return table_name

        return sheet_name

    def from_rows(
        self,
        rows: list[Mapping[str, Any]],
    ) -> dict[str, TableRuleConfiguration]:
        try:
            grouped: dict[str, list[Mapping[str, Any]]] = {}

            for row in rows:
                table_name = str(row.get("Table", "") or "").strip()

                if not table_name:
                    continue

                grouped.setdefault(table_name, []).append(row)

            result: dict[str, TableRuleConfiguration] = {}

            for table_name, table_rows in grouped.items():
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
        return list(frame.iter_rows(named=True))

    @staticmethod
    def _normalize_keys(
        row: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return {str(key).strip(): value for key, value in row.items()}

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True

        return isinstance(value, float) and value != value

    @classmethod
    def _clean_text(cls, value: Any, default: str = "") -> str:
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
        if cls._is_missing(value):
            return ""

        return value
