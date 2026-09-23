"""Builds the flat Failed Rows summary (for CSV/API export) and writes the native per-table Excel rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter

from engine.core.result_models import ValidationRunResult
from engine.reporting.failed_rows_formatter import (
    DQ_RULE_REFERENCE_COLUMN,
    ROW_INDEX_COLUMN,
    FailedRowsFormatter,
)
from engine.reporting.failed_rows_workbook_writer import (
    ROW_ID_COLUMN,
    FailedRowsWorkbookWriter,
)
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger


logger = get_logger(__name__)


def _frame(rows: list[dict], columns: list[str]) -> pl.DataFrame:
    """Build a report frame with a fixed column order.

    An explicit schema is required for the empty case: polars cannot infer
    columns from no rows, and the writers still expect the headers to exist so
    an empty sheet renders with its header row rather than blank.
    """
    if not rows:
        return pl.DataFrame(schema={name: pl.Utf8 for name in columns})

    return pl.DataFrame(rows).select(columns)


class FailedRowsReport:
    """Builds failed-row data for both the flat DataFrame export and the native Excel rendering."""

    SHEET_NAME = "Failed Rows"

    def __init__(
        self,
        formatter: FailedRowsFormatter | None = None,
        workbook_writer: FailedRowsWorkbookWriter | None = None,
    ) -> None:
        """Store the formatter and workbook writer collaborators."""
        self.formatter = formatter or FailedRowsFormatter()
        self.workbook_writer = (
            workbook_writer
            or FailedRowsWorkbookWriter(formatter=self.formatter)
        )

    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> pl.DataFrame:
        """Build a flat summary of failed rows (one row per rejected record) for CSV/API export.

        write_to_workbook() does not use this DataFrame - it renders directly from
        validation_result so each table keeps its own original columns and per-cell highlighting.
        """
        try:
            rows: list[dict[str, Any]] = []

            for table_name, table_result in validation_result.tables.items():
                if table_result.failed_rows is None or table_result.fail_count == 0:
                    continue

                failed_rows = table_result.failed_rows

                row_ids = [
                    row[ROW_ID_COLUMN]
                    for row in failed_rows.select(ROW_ID_COLUMN).collect()
                ]

                for row_index in row_ids:
                    failures = self.formatter.sort_failures(
                        table_result.row_failures.get(
                            row_index,
                            [],
                        )
                    )

                    rows.append(
                        {
                            "Table": table_name,
                            ROW_INDEX_COLUMN: row_index,
                            DQ_RULE_REFERENCE_COLUMN: self.formatter.reference_string(
                                failures
                            ),
                        }
                    )

            dataframe = _frame(
                rows,
                [
                    "Table",
                    ROW_INDEX_COLUMN,
                    DQ_RULE_REFERENCE_COLUMN,
                ],
            )

            logger.debug(
                "Built failed-rows report with %s rows",
                len(dataframe),
            )

            return dataframe

        except Exception:
            logger.exception(
                "Failed to build failed-rows report"
            )
            raise

    def write(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
        sheet_name: str = SHEET_NAME,
    ) -> Path:
        """Write the Failed Rows sheet to a standalone workbook."""
        output_path = Path(output_path)

        try:
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            # xlsxwriter directly rather than through a dataframe library's
            # writer wrapper: every cell below is written with the xlsxwriter
            # API anyway, so the wrapper only added a dependency.
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
                "Wrote failed-rows report to '%s'",
                output_path,
            )

            return output_path

        except Exception:
            logger.exception(
                "Failed to write failed-rows report '%s'",
                output_path,
            )
            raise

    def write_to_workbook(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
        sheet_name: str = SHEET_NAME,
    ) -> None:
        """Add the Failed Rows worksheet and delegate its layout to FailedRowsWorkbookWriter."""
        try:
            workbook = getattr(writer, "book", writer)
            worksheet = workbook.add_worksheet(sheet_name)

            self.workbook_writer.write(
                workbook=workbook,
                worksheet=worksheet,
                validation_result=validation_result,
            )

            logger.debug(
                "Wrote failed-rows sheet '%s'",
                sheet_name,
            )

        except Exception:
            logger.exception(
                "Failed to write failed-rows sheet '%s'",
                sheet_name,
            )
            raise
