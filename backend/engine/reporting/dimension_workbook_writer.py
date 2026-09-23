"""Writes one dimension report DataFrame into an xlsxwriter worksheet: colors, formats, header block, and data rows."""

from __future__ import annotations

from typing import Any

import polars as pl

from common.files.excel_safety import is_missing

from engine.reporting.dimension_scorer import DimensionScorer


class DimensionWorkbookWriter:
    """Lays out a dimension report sheet in xlsxwriter, given a dataframe and label/definition text."""

    DARK_BLUE = "#1F4E79"
    MED_BLUE = "#2E75B6"
    ALT_BLUE = "#EBF3FB"
    GREEN_FILL = "#E2EFDA"
    YELLOW_FILL = "#FFF2CC"
    RED_FILL = "#FFDAD6"
    WHITE = "#FFFFFF"

    COLUMN_WIDTHS = [5, 32, 28, 6, 8, 45, 14, 13, 10, 14]

    HEADER_ROW = 3

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
    ) -> None:
        """Store the scorer used for score formatting and grading."""
        self.scorer = scorer or DimensionScorer()

    def write(
        self,
        workbook: Any,
        worksheet: Any,
        dataframe: pl.DataFrame,
        dimension_label: str,
        measurement: str,
        control: str,
    ) -> None:
        """Fill an already-created worksheet with one dimension's report."""

        formats = self._create_formats(workbook)
        overall_score = self.scorer.overall_score(dataframe)

        self._write_definition_header(
            worksheet=worksheet,
            dimension_label=dimension_label,
            measurement=measurement,
            control=control,
            overall_score=overall_score,
            formats=formats,
        )

        self._write_header_row(
            worksheet=worksheet,
            columns=list(dataframe.columns),
            formats=formats,
        )

        self._write_data(
            worksheet=worksheet,
            dataframe=dataframe,
            formats=formats,
        )

        self._configure_worksheet(worksheet)

    def _create_formats(
        self,
        workbook: Any,
    ) -> dict[str, Any]:
        """Build the named xlsxwriter cell formats used across this sheet."""
        return {
            "meta_label": workbook.add_format({"bold": True}),
            "meta_value": workbook.add_format({}),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": self.MED_BLUE,
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

    def _write_definition_header(
        self,
        worksheet: Any,
        dimension_label: str,
        measurement: str,
        control: str,
        overall_score: float,
        formats: dict[str, Any],
    ) -> None:
        """Write the sheet's top metadata block (dimension name, measurement, control, overall score)."""
        worksheet.write(0, 0, dimension_label, formats["meta_label"])

        worksheet.write(1, 0, "Measurement", formats["meta_label"])
        worksheet.write(1, 1, measurement, formats["meta_value"])
        worksheet.write(1, 3, "Overall Score", formats["meta_label"])
        worksheet.write(
            1,
            4,
            self.scorer.format_score(overall_score),
            formats["meta_value"],
        )

        worksheet.write(2, 0, "Control", formats["meta_label"])
        worksheet.write(2, 1, control, formats["meta_value"])

        worksheet.set_row(1, 20)
        worksheet.set_row(2, 20)

    def _write_header_row(
        self,
        worksheet: Any,
        columns: list[str],
        formats: dict[str, Any],
    ) -> None:
        """Write the column header row."""
        for column_index, column_name in enumerate(columns):
            worksheet.write(
                self.HEADER_ROW,
                column_index,
                column_name,
                formats["header"],
            )

        worksheet.set_row(self.HEADER_ROW, 30)

    INTEGER_COLUMNS = {"#", "Invalid Count", "Total Count"}

    def _write_data(
        self,
        worksheet: Any,
        dataframe: pl.DataFrame,
        formats: dict[str, Any],
    ) -> None:
        """Write every data row, then apply column widths."""
        for row_index in range(len(dataframe)):
            self._write_row(
                worksheet=worksheet,
                dataframe=dataframe,
                row_index=row_index,
                formats=formats,
            )

        self._format_columns(worksheet)

    def _write_row(
        self,
        worksheet: Any,
        dataframe: pl.DataFrame,
        row_index: int,
        formats: dict[str, Any],
    ) -> None:
        """Write one data row, alternating row shading."""
        excel_row = self.HEADER_ROW + 1 + row_index
        is_alt = (row_index + 1) % 2 == 0

        for column_index, column_name in enumerate(dataframe.columns):
            self._write_cell(
                worksheet=worksheet,
                excel_row=excel_row,
                column_index=column_index,
                column_name=column_name,
                value=dataframe[row_index, column_index],
                is_alt=is_alt,
                formats=formats,
            )

    def _write_cell(
        self,
        worksheet: Any,
        excel_row: int,
        column_index: int,
        column_name: str,
        value: Any,
        is_alt: bool,
        formats: dict[str, Any],
    ) -> None:
        """Dispatch a cell to the score, integer, or text writer based on its column."""
        if column_name == "Score":
            self._write_score_cell(worksheet, excel_row, column_index, value, formats)
        elif column_name in self.INTEGER_COLUMNS:
            self._write_integer_cell(worksheet, excel_row, column_index, value, is_alt, formats)
        else:
            self._write_text_cell(worksheet, excel_row, column_index, value, is_alt, formats)

    def _write_score_cell(
        self,
        worksheet: Any,
        excel_row: int,
        column_index: int,
        value: Any,
        formats: dict[str, Any],
    ) -> None:
        """Write a Score cell, colored by its good/warning/poor grade."""
        score = self.scorer.safe_score(value)

        worksheet.write(
            excel_row,
            column_index,
            self.scorer.format_score(score),
            self._score_format(score, formats),
        )

    def _write_integer_cell(
        self,
        worksheet: Any,
        excel_row: int,
        column_index: int,
        value: Any,
        is_alt: bool,
        formats: dict[str, Any],
    ) -> None:
        """Write a numeric cell (#, Invalid Count, Total Count)."""
        worksheet.write_number(
            excel_row,
            column_index,
            self.scorer.safe_integer(value),
            formats["center_alt" if is_alt else "center"],
        )

    def _write_text_cell(
        self,
        worksheet: Any,
        excel_row: int,
        column_index: int,
        value: Any,
        is_alt: bool,
        formats: dict[str, Any],
    ) -> None:
        """Write a plain text cell."""
        worksheet.write(
            excel_row,
            column_index,
            self._excel_value(value),
            formats["text_alt" if is_alt else "text"],
        )

    def _format_columns(
        self,
        worksheet: Any,
    ) -> None:
        """Apply the configured column widths."""
        for column_index, width in enumerate(self.COLUMN_WIDTHS):
            worksheet.set_column(column_index, column_index, width)

    def _configure_worksheet(
        self,
        worksheet: Any,
    ) -> None:
        """Freeze panes below the header row."""
        worksheet.freeze_panes(self.HEADER_ROW + 1, 0)

    @staticmethod
    def _excel_value(value: Any) -> Any:
        """Replace NaN with an empty string for Excel output."""
        if is_missing(value):
            return ""

        return value

    def _score_format(
        self,
        score: float,
        formats: dict[str, Any],
    ) -> Any:
        """Return the cell format matching a score's good/warning/poor grade."""
        return formats[self.scorer.bucket(score)]
