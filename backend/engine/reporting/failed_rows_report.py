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
    if not rows:
        return pl.DataFrame(schema={name: pl.Utf8 for name in columns})

    return pl.DataFrame(rows).select(columns)


class FailedRowsReport:
    SHEET_NAME = "Failed Rows"

    def __init__(
        self,
        formatter: FailedRowsFormatter | None = None,
        workbook_writer: FailedRowsWorkbookWriter | None = None,
    ) -> None:
        self.formatter = formatter or FailedRowsFormatter()
        self.workbook_writer = (
            workbook_writer
            or FailedRowsWorkbookWriter(formatter=self.formatter)
        )

    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> pl.DataFrame:
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
        output_path = Path(output_path)

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
