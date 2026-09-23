from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Iterable

from engine.core.result_models import RowFailure, ValidationRunResult
from engine.reporting.failed_rows_formatter import (
    DQ_RULE_REFERENCE_COLUMN,
    FailedRowsFormatter,
)


MAX_FORMATTED_COLUMNS = 50
COLUMN_WIDTH = 22

ROW_ID_COLUMN = "_dq_row_id"


class FailedRowsWorkbookWriter:
    TITLE = "Failed / Rejected Rows by Table"

    MED_BLUE = "#2E75B6"
    RED_FILL = "#FFDAD6"
    WHITE = "#FFFFFF"
    TABLE_LABEL_COLOR = "#CC0000"
    FAILED_FONT_COLOR = "#9C0006"

    def __init__(
        self,
        formatter: FailedRowsFormatter | None = None,
    ) -> None:
        self.formatter = formatter or FailedRowsFormatter()

    def write(
        self,
        workbook: Any,
        worksheet: Any,
        validation_result: ValidationRunResult,
    ) -> None:
        formats = self._create_formats(workbook)

        worksheet.write(0, 0, self.TITLE, formats["title"])

        current_row = 2
        max_columns = 1

        for table_name, table_result in validation_result.tables.items():
            if table_result.failed_rows is None or table_result.fail_count == 0:
                continue

            failed_rows = table_result.failed_rows.toLocalIterator()

            current_row, columns_used = self._write_table_block(
                worksheet=worksheet,
                table_name=table_name,
                columns=[
                    column
                    for column in table_result.failed_rows.columns
                    if column != ROW_ID_COLUMN
                ],
                failed_rows=failed_rows,
                failed_row_count=table_result.fail_count,
                row_failures=table_result.row_failures,
                start_row=current_row,
                formats=formats,
            )

            max_columns = max(max_columns, columns_used)

        self._format_columns(
            worksheet=worksheet,
            column_count=max_columns,
        )

    def _write_table_block(
        self,
        worksheet: Any,
        table_name: str,
        columns: list[str],
        failed_rows: Iterable[Any],
        failed_row_count: int,
        row_failures: dict[Any, list[RowFailure]],
        start_row: int,
        formats: dict[str, Any],
    ) -> tuple[int, int]:
        row = start_row

        worksheet.write(
            row,
            0,
            f"Table: {table_name}",
            formats["table_label"],
        )

        worksheet.write(
            row,
            1,
            f"Rejected rows: {failed_row_count}",
        )

        row += 1

        headers = [
            DQ_RULE_REFERENCE_COLUMN
        ] + columns

        for column_index, header in enumerate(headers):
            worksheet.write(
                row,
                column_index,
                header,
                formats["header"],
            )

        for spark_row in failed_rows:
            row += 1

            row_index = spark_row[ROW_ID_COLUMN]

            failures = self.formatter.sort_failures(
                row_failures.get(
                    row_index,
                    [],
                )
            )

            failed_columns = {
                failure.column_name
                for failure in failures
            }

            row_values = [
                self.formatter.reference_string(failures)
            ] + [
                self._excel_value(spark_row[column])
                for column in columns
            ]

            for column_index, value in enumerate(row_values):
                if column_index == 0:
                    worksheet.write(
                        row,
                        column_index,
                        value,
                        formats["failed"],
                    )
                    continue

                column_name = columns[column_index - 1]

                is_failed = column_name in failed_columns

                if isinstance(value, datetime):
                    cell_format = (
                        formats["failed_datetime"]
                        if is_failed
                        else formats["normal_datetime"]
                    )
                elif isinstance(value, date):
                    cell_format = (
                        formats["failed_date"]
                        if is_failed
                        else formats["normal_date"]
                    )
                else:
                    cell_format = (
                        formats["failed"]
                        if is_failed
                        else formats["normal"]
                    )
                worksheet.write(
                    row,
                    column_index,
                    value,
                    cell_format,
                )
                
            worksheet.set_row(
                row,
                self._row_height(len(failures)),
            )

        row += 2

        return row, len(headers)

    def _create_formats(
        self,
        workbook: Any,
    ) -> dict[str, Any]:
        return {
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 12,
                }
            ),
            "table_label": workbook.add_format(
                {
                    "bold": True,
                    "font_color": self.TABLE_LABEL_COLOR,
                }
            ),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": self.MED_BLUE,
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                    "border": 1,
                }
            ),
            "normal": workbook.add_format(
                {
                    "bg_color": self.WHITE,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                }
            ),
            "failed": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": self.RED_FILL,
                    "font_color": self.FAILED_FONT_COLOR,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                }
            ),
            "normal_date": workbook.add_format(
                {
                    "bg_color": self.WHITE,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                    "num_format": "yyyy-mm-dd",
                }
            ),
            "failed_date": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": self.RED_FILL,
                    "font_color": self.FAILED_FONT_COLOR,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                    "num_format": "yyyy-mm-dd",
                }
            ),
            "normal_datetime": workbook.add_format(
                {
                    "bg_color": self.WHITE,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                    "num_format": "yyyy-mm-dd hh:mm:ss",
                }
            ),
            "failed_datetime": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": self.RED_FILL,
                    "font_color": self.FAILED_FONT_COLOR,
                    "align": "left",
                    "valign": "top",
                    "text_wrap": True,
                    "border": 1,
                    "num_format": "yyyy-mm-dd hh:mm:ss",
                }
            ),
        }
    
    def _format_columns(
        self,
        worksheet: Any,
        column_count: int,
    ) -> None:
        column_count = min(
            max(column_count, 1),
            MAX_FORMATTED_COLUMNS,
        )

        worksheet.set_column(
            0,
            column_count - 1,
            COLUMN_WIDTH,
        )

    @staticmethod
    def _row_height(
        failure_count: int,
    ) -> float:
        lines = max(failure_count, 1)

        return min(15 * lines + 5, 120)

    @staticmethod
    def _is_missing(
        value: Any,
    ) -> bool:
        if value is None:
            return True

        if isinstance(value, float) and math.isnan(value):
            return True

        return False

    @staticmethod
    def _is_date_value(
        value: Any,
    ) -> bool:
        return isinstance(value, (date, datetime))
    
    @staticmethod
    def _excel_value(
        value: Any,
    ) -> Any:
        if FailedRowsWorkbookWriter._is_missing(value):
            return ""

        if isinstance(value, (date, datetime)):
            return value

        if isinstance(value, (list, tuple, set)):
            return ", ".join(
                str(item)
                for item in value
            )

        if isinstance(value, dict):
            return str(value)

        return value