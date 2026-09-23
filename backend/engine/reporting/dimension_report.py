from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter

from engine.core.result_models import (
    RuleExecutionDetail,
    ValidationRunResult,
)
from engine.reporting.dimension_scorer import DimensionScorer
from engine.reporting.dimension_workbook_writer import DimensionWorkbookWriter
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger


logger = get_logger(__name__)


def _frame(rows: list[dict], columns: list[str]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema={name: pl.Utf8 for name in columns})

    return pl.DataFrame(rows).select(columns)


class DimensionReport:
    DEFAULT_COLUMNS = [
        "#",
        "Table",
        "Column",
        "CDE",
        "Rule ID",
        "Rule Notes",
        "Invalid Count",
        "Total Count",
        "Score",
        "Score Bar",
    ]

    DIMENSION_ORDER = [
        "Completeness",
        "Conformity",
        "Consistency",
        "Uniqueness",
        "Custom",
    ]

    DEFINITIONS = {
        "Completeness": (
            "Completeness = [(Total Count – Null Count) / Total Count]",
            "Validation of data for Critical fields at Point of Entry",
        ),
        "Conformity": (
            "Conformity = [(Total Count – Invalid Count) / Total Count]",
            "Implementation of all Business rules for all conditions",
        ),
        "Consistency": (
            "Consistency = (No of records Passed rule / Total records) x 100",
            "Check data against business definitions and reference values",
        ),
        "Uniqueness": (
            "Uniqueness = (Unique Count / Total Count)",
            "Validation of data for Critical fields at Point of Entry",
        ),
        "Custom": (
            "Custom rule score = Pass Count / Total Count",
            "Custom expressions",
        ),
    }

    SHEET_NAME_LIMIT = 31

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
        workbook_writer: DimensionWorkbookWriter | None = None,
    ) -> None:
        self.scorer = scorer or DimensionScorer()
        self.workbook_writer = (
            workbook_writer
            or DimensionWorkbookWriter(scorer=self.scorer)
        )

    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> dict[str, pl.DataFrame]:
        try:
            dimension_rows: dict[str, list[Any]] = {}

            for table_result in validation_result.tables.values():
                for detail in table_result.rule_details:
                    dimension = self._normalize_dimension(detail.dimension)

                    if not dimension:
                        dimension = "Custom"

                    dimension_rows.setdefault(dimension, []).append(detail)

            reports: dict[str, pl.DataFrame] = {}

            for dimension in self._ordered_dimensions(dimension_rows):
                reports[self._sheet_name(dimension)] = self._to_dataframe(
                    dimension_rows.get(dimension, [])
                )

            logger.debug("Built %s dimension report sheets", len(reports))
            return reports

        except Exception:
            logger.exception("Failed to build dimension reports")
            raise

    def build_dimension(
        self,
        validation_result: ValidationRunResult,
        dimension: str,
    ) -> pl.DataFrame:
        try:
            normalized_dimension = self._normalize_dimension(dimension)

            details: list[RuleExecutionDetail] = []

            for table_result in validation_result.tables.values():
                for detail in table_result.rule_details:
                    detail_dimension = self._normalize_dimension(detail.dimension)

                    if not detail_dimension:
                        detail_dimension = "Custom"

                    if detail_dimension != normalized_dimension:
                        continue

                    details.append(detail)

            return self._to_dataframe(details)

        except Exception:
            logger.exception("Failed to build dimension '%s'", dimension)
            raise

    def write(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
        sheet_name: str | None = None,
    ) -> Path:
        output_path = Path(output_path)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with xlsxwriter.Workbook(
                str(output_path),
                XLSXWRITER_SAFE_OPTIONS,
            ) as writer:

                if sheet_name is not None:
                    dimension = self._dimension_from_sheet_name(sheet_name)
                    dataframe = self.build_dimension(validation_result, dimension)

                    self.write_to_workbook(
                        writer=writer,
                        dataframe=dataframe,
                        sheet_name=sheet_name,
                        dimension=dimension,
                    )

                else:
                    reports = self.build(validation_result)

                    for report_sheet_name, dataframe in reports.items():
                        dimension = self._dimension_from_sheet_name(report_sheet_name)

                        self.write_to_workbook(
                            writer=writer,
                            dataframe=dataframe,
                            sheet_name=report_sheet_name,
                            dimension=dimension,
                        )

            logger.info("Wrote dimension reports to '%s'", output_path)
            return output_path

        except Exception:
            logger.exception("Failed to write dimension report '%s'", output_path)
            raise

    def write_to_workbook(
        self,
        writer: Any,
        dataframe: pl.DataFrame,
        sheet_name: str,
        dimension: str | None = None,
    ) -> None:
        try:
            workbook = getattr(writer, "book", writer)
            safe_sheet_name = self._sheet_name(sheet_name)

            if workbook.get_worksheet_by_name(safe_sheet_name) is not None:
                raise ValueError(f"Worksheet '{safe_sheet_name}' already exists.")

            worksheet = workbook.add_worksheet(safe_sheet_name)

            dimension_label = dimension or safe_sheet_name
            measurement, control = self.DEFINITIONS.get(
                dimension_label,
                ("-", "-"),
            )

            self.workbook_writer.write(
                workbook=workbook,
                worksheet=worksheet,
                dataframe=dataframe,
                dimension_label=dimension_label,
                measurement=measurement,
                control=control,
            )

            logger.debug("Wrote dimension sheet '%s'", safe_sheet_name)

        except Exception:
            logger.exception("Failed to write dimension sheet '%s'", sheet_name)
            raise

    def _to_dataframe(
        self,
        details: list[RuleExecutionDetail],
    ) -> pl.DataFrame:
        rows = [
            self._detail_to_row(index=index, detail=detail)
            for index, detail in enumerate(details, start=1)
        ]

        return _frame(rows, self.DEFAULT_COLUMNS)

    def _detail_to_row(
        self,
        index: int,
        detail: RuleExecutionDetail,
    ) -> dict[str, Any]:
        return {
            "#": index,
            "Table": detail.table_name,
            "Column": detail.column_name,
            "CDE": "X" if detail.cde else "",
            "Rule ID": detail.rule_id,
            "Rule Notes": detail.rule_notes,
            "Invalid Count": detail.invalid_count,
            "Total Count": detail.total_rows,
            "Score": detail.score,
            "Score Bar": self.scorer.score_bar(detail.score),
        }

    def _ordered_dimensions(
        self,
        dimension_rows: dict[str, list[Any]],
    ) -> list[str]:
        existing = list(dimension_rows.keys())

        ordered = [
            dimension
            for dimension in self.DIMENSION_ORDER
            if dimension in existing
        ]

        remaining = sorted(
            dimension
            for dimension in existing
            if dimension not in ordered
        )

        ordered.extend(remaining)
        return ordered

    @staticmethod
    def _normalize_dimension(dimension: Any) -> str:
        if dimension is None:
            return ""

        return str(dimension).strip()

    def _sheet_name(self, dimension: str) -> str:
        name = str(dimension).strip()

        if not name:
            name = "Custom"

        invalid_characters = ["\\", "/", "*", "?", ":", "[", "]"]

        for character in invalid_characters:
            name = name.replace(character, "_")

        if not name:
            name = "Custom"

        return name[: self.SHEET_NAME_LIMIT]

    @staticmethod
    def _dimension_from_sheet_name(sheet_name: str) -> str:
        return str(sheet_name).strip()
