from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter

from engine.core.result_models import ValidationRunResult
from engine.reporting.dimension_scorer import DimensionScorer
from engine.reporting.summary_workbook_writer import SummaryWorkbookWriter
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger


logger = get_logger(__name__)


def _frame(rows: list[dict], columns: list[str]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema={name: pl.Utf8 for name in columns})

    return pl.DataFrame(rows).select(columns)


class SummaryReport:
    SHEET_NAME = "Summary"

    DIMENSION_ORDER = [
        "Completeness",
        "Conformity",
        "Consistency",
        "Uniqueness",
        "Accuracy",
        "Custom",
    ]

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
        workbook_writer: SummaryWorkbookWriter | None = None,
    ) -> None:
        self.scorer = scorer or DimensionScorer()
        self.workbook_writer = (
            workbook_writer
            or SummaryWorkbookWriter(scorer=self.scorer)
        )

    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> pl.DataFrame:
        try:
            rows: list[dict[str, Any]] = []

            for dimension_name in self._ordered_dimensions(
                validation_result
            ):
                dimension_result = (
                    validation_result.summary.dimension_results[
                        dimension_name
                    ]
                )

                score = dimension_result.score

                rows.append(
                    {
                        "Dimension": dimension_name,
                        "Score": score,
                        "Status": self.scorer.bucket(score).capitalize(),
                    }
                )

            dataframe = _frame(
                rows,
                [
                    "Dimension",
                    "Score",
                    "Status",
                ],
            )

            logger.debug(
                "Built summary report with %s rows",
                len(dataframe),
            )

            return dataframe

        except Exception:
            logger.exception(
                "Failed to build summary report"
            )
            raise

    def write(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
        sheet_name: str = SHEET_NAME,
    ) -> Path:
        output_path = Path(
            output_path
        )

        try:
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with xlsxwriter.Workbook(
                str(output_path),
                XLSXWRITER_SAFE_OPTIONS,
            ) as writer:

                self.write_to_workbook(
                    writer=writer,
                    validation_result=validation_result,
                    sheet_name=sheet_name,
                )

            logger.info(
                "Wrote summary report to '%s'",
                output_path,
            )

            return output_path

        except Exception:
            logger.exception(
                "Failed to write summary report '%s'",
                output_path,
            )
            raise

    def write_to_workbook(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
        sheet_name: str = SHEET_NAME,
    ) -> None:
        try:
            workbook = getattr(writer, "book", writer)
            worksheet = workbook.add_worksheet(
                sheet_name
            )

            dataframe = self.build(
                validation_result
            )

            self.workbook_writer.write(
                workbook=workbook,
                worksheet=worksheet,
                dataframe=dataframe,
                project_name=validation_result.project_name,
                run_timestamp=validation_result.run_timestamp,
                overall_score=validation_result.summary.overall_score,
                validation_result=validation_result,
            )

            logger.debug(
                "Wrote formatted summary sheet '%s'",
                sheet_name,
            )

        except Exception:
            logger.exception(
                "Failed to write summary sheet '%s'",
                sheet_name,
            )
            raise

    def _ordered_dimensions(
        self,
        validation_result: ValidationRunResult,
    ) -> list[str]:
        existing = list(
            validation_result.summary.dimension_results.keys()
        )

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

        ordered.extend(
            remaining
        )

        return ordered
