from __future__ import annotations

import math
from typing import Any

from pyspark.sql import DataFrame

from engine.reporting.dimension_scorer import DimensionScorer


class AllFindingsWorkbookWriter:
    DARK_BLUE = "#1F4E79"
    ALT_BLUE = "#EBF3FB"
    GREEN_FILL = "#E2EFDA"
    YELLOW_FILL = "#FFF2CC"
    RED_FILL = "#FFDAD6"
    WHITE = "#FFFFFF"

    COLUMN_WIDTHS = [5, 32, 28, 6, 16, 8, 50, 14, 12, 12, 10]

    INTEGER_COLUMNS = {
        "#",
        "Invalid Count",
        "Total Rows",
        "Pass Count",
    }

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
    ) -> None:
        self.scorer = scorer or DimensionScorer()

    def write(
        self,
        workbook: Any,
        worksheet: Any,
        dataframe: DataFrame,
    ) -> int:
        formats = self._create_formats(workbook)
        rows = dataframe.collect()

        self._format_header(worksheet, dataframe, formats)
        self._format_data(worksheet, dataframe, rows, formats)
        self._format_columns(worksheet)
        self._configure_worksheet(worksheet, dataframe, len(rows))

        return len(rows)

    def _create_formats(
        self,
        workbook: Any,
    ) -> dict[str, Any]:
        return {
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": self.DARK_BLUE,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "text": workbook.add_format(
                {
                    "border": 1,
                    "valign": "top",
                    "text_wrap": True,
                    "bg_color": self.WHITE,
                }
            ),
            "text_alt": workbook.add_format(
                {
                    "border": 1,
                    "valign": "top",
                    "text_wrap": True,
                    "bg_color": self.ALT_BLUE,
                }
            ),
            "center": workbook.add_format(
                {
                    "border": 1,
                    "align": "center",
                    "valign": "top",
                    "bg_color": self.WHITE,
                }
            ),
            "center_alt": workbook.add_format(
                {
                    "border": 1,
                    "align": "center",
                    "valign": "top",
                    "bg_color": self.ALT_BLUE,
                }
            ),
            "good": workbook.add_format(
                {
                    "border": 1,
                    "align": "center",
                    "valign": "top",
                    "bg_color": self.GREEN_FILL,
                }
            ),
            "warning": workbook.add_format(
                {
                    "border": 1,
                    "align": "center",
                    "valign": "top",
                    "bg_color": self.YELLOW_FILL,
                }
            ),
            "poor": workbook.add_format(
                {
                    "border": 1,
                    "align": "center",
                    "valign": "top",
                    "bg_color": self.RED_FILL,
                }
            ),
        }

    def _format_header(
        self,
        worksheet: Any,
        dataframe: DataFrame,
        formats: dict[str, Any],
    ) -> None:
        for column_index, column_name in enumerate(dataframe.columns):
            worksheet.write(0, column_index, column_name, formats["header"])

        worksheet.set_row(0, 30)

    def _format_data(
        self,
        worksheet: Any,
        dataframe: DataFrame,
        rows: list[Any],
        formats: dict[str, Any],
    ) -> None:
        for row_index, row in enumerate(rows):
            excel_row_number = row_index + 2
            is_alt = excel_row_number % 2 == 0

            for column_index, column_name in enumerate(dataframe.columns):
                value = row[column_name]

                if column_name == "Score":
                    self._write_score_cell(
                        worksheet=worksheet,
                        row_index=row_index,
                        column_index=column_index,
                        value=value,
                        formats=formats,
                    )

                elif column_name in self.INTEGER_COLUMNS:
                    worksheet.write_number(
                        row_index + 1,
                        column_index,
                        self.scorer.safe_integer(value),
                        formats["center_alt" if is_alt else "center"],
                    )

                else:
                    worksheet.write(
                        row_index + 1,
                        column_index,
                        self._excel_value(value),
                        formats["text_alt" if is_alt else "text"],
                    )

    def _write_score_cell(
        self,
        worksheet: Any,
        row_index: int,
        column_index: int,
        value: Any,
        formats: dict[str, Any],
    ) -> None:
        score = self.scorer.safe_score(value)

        worksheet.write(
            row_index + 1,
            column_index,
            self.scorer.format_score(score),
            formats[self.scorer.bucket(score)],
        )

    def _format_columns(
        self,
        worksheet: Any,
    ) -> None:
        for column_index, width in enumerate(self.COLUMN_WIDTHS):
            worksheet.set_column(column_index, column_index, width)

    @staticmethod
    def _configure_worksheet(
        worksheet: Any,
        dataframe: DataFrame,
        row_count: int,
    ) -> None:
        worksheet.freeze_panes(1, 0)

        if len(dataframe.columns) > 0:
            worksheet.autofilter(
                0,
                0,
                max(row_count, 1),
                len(
                    dataframe.columns
                ) - 1,
            )

    @staticmethod
    def _excel_value(value: Any) -> Any:
        if value is None:
            return ""

        if isinstance(value, float) and math.isnan(value):
            return ""

        return value
