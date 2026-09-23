from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl

from engine.reporting.dimension_scorer import DimensionScorer


class SummaryWorkbookWriter:
    TITLE = "Data Quality Analysis – Summary"

    DARK_BLUE = "#1F4E79"
    MED_BLUE = "#2E75B6"
    LIGHT_BLUE = "#D6E4F0"
    GREEN_FILL = "#E2EFDA"
    YELLOW_FILL = "#FFF2CC"
    RED_FILL = "#FFDAD6"
    WHITE = "#FFFFFF"

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
    ) -> None:
        self.scorer = scorer or DimensionScorer()

    def write(
        self,
        workbook: Any,
        worksheet: Any,
        dataframe: pl.DataFrame,
        project_name: str,
        run_timestamp: str,
        overall_score: float,
        validation_result: Any = None,
    ) -> None:
        formats = self._create_formats(workbook)

        self._configure_worksheet(worksheet)
        self._write_title(worksheet, formats)

        self._write_project_metadata(
            worksheet=worksheet,
            project_name=project_name,
            run_timestamp=run_timestamp,
            formats=formats,
            validation_result=validation_result,
        )

        dimension_count = self._write_dimension_section(
            worksheet=worksheet,
            dataframe=dataframe,
            formats=formats,
        )

        overall_row = self._write_overall_score(
            worksheet=worksheet,
            overall_score=overall_score,
            formats=formats,
            dimension_count=dimension_count,
        )

        self._write_legend(
            worksheet=worksheet,
            formats=formats,
            overall_row=overall_row,
        )

    def _create_formats(
        self,
        workbook: Any,
    ) -> dict[str, Any]:
        return {
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 16,
                    "font_color": self.WHITE,
                    "bg_color": self.DARK_BLUE,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            "project_meta": workbook.add_format(
                {
                    "font_color": self.WHITE,
                    "bg_color": self.MED_BLUE,
                    "font_size": 10,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "bg_color": self.LIGHT_BLUE,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            "dimension_label": workbook.add_format(
                {
                    "bold": True,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            "row_good": workbook.add_format(
                {
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.GREEN_FILL,
                }
            ),
            "row_warning": workbook.add_format(
                {
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.YELLOW_FILL,
                }
            ),
            "row_poor": workbook.add_format(
                {
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.RED_FILL,
                }
            ),
            "overall_label": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 11,
                    "align": "left",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            "overall_good": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 11,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.GREEN_FILL,
                }
            ),
            "overall_warning": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 11,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.YELLOW_FILL,
                }
            ),
            "overall_poor": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 11,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                    "bg_color": self.RED_FILL,
                }
            ),
            "legend_label": workbook.add_format(
                {
                    "bold": True,
                }
            ),
            "legend_good": workbook.add_format(
                {
                    "bg_color": self.GREEN_FILL,
                }
            ),
            "legend_warning": workbook.add_format(
                {
                    "bg_color": self.YELLOW_FILL,
                }
            ),
            "legend_poor": workbook.add_format(
                {
                    "bg_color": self.RED_FILL,
                }
            ),
        }

    def _configure_worksheet(
        self,
        worksheet: Any,
    ) -> None:
        worksheet.set_column("A:A", 28)
        worksheet.set_column("B:B", 20)
        worksheet.set_column("C:C", 22)
        worksheet.set_row(0, 36)

    def _write_title(
        self,
        worksheet: Any,
        formats: dict[str, Any],
    ) -> None:
        worksheet.merge_range(0, 0, 0, 2, self.TITLE, formats["title"])

    def _write_project_metadata(
        self,
        worksheet: Any,
        project_name: str,
        run_timestamp: str,
        formats: dict[str, Any],
        validation_result: Any = None,
    ) -> None:
        generated = self._format_timestamp(run_timestamp)

        total_executed = sum(
            len(table.rule_details) for table in validation_result.tables.values()
        ) if validation_result else 0
        total_configured = validation_result.metadata.get("total_configured_rules", total_executed) if validation_result else 0

        text = f"Project: {project_name}   |   Generated: {generated}   |   Rules Executed: {total_executed} / {total_configured}"

        worksheet.merge_range(
            1,
            0,
            1,
            2,
            text,
            formats["project_meta"],
        )

    def _write_dimension_section(
        self,
        worksheet: Any,
        dataframe: pl.DataFrame,
        formats: dict[str, Any],
    ) -> int:
        header_row = 3

        worksheet.write(header_row, 0, "Dimension", formats["header"])
        worksheet.write(header_row, 1, "Score", formats["header"])
        worksheet.write(header_row, 2, "Status", formats["header"])

        row = header_row + 1

        for record in dataframe.iter_rows(named=True):
            status = str(record["Status"])
            score = float(record["Score"])
            row_format = self._row_format(status.lower(), formats)

            worksheet.write(row, 0, record["Dimension"], formats["dimension_label"])
            worksheet.write(
                row, 1, self.scorer.format_score(score, precision=1), row_format
            )
            worksheet.write(row, 2, status, row_format)

            row += 1

        return len(dataframe)

    def _write_overall_score(
        self,
        worksheet: Any,
        overall_score: float,
        formats: dict[str, Any],
        dimension_count: int,
    ) -> int:
        row = 4 + dimension_count

        overall_score = float(overall_score)
        status = self.scorer.bucket(overall_score)

        worksheet.merge_range(row, 0, row, 1, "Overall DQ Score", formats["overall_label"])

        worksheet.write(
            row,
            2,
            self.scorer.format_score(overall_score, precision=1),
            self._overall_format(status, formats),
        )

        return row

    def _write_legend(
        self,
        worksheet: Any,
        formats: dict[str, Any],
        overall_row: int,
    ) -> None:
        row = overall_row + 2
        good_pct = int(self.scorer.GOOD_THRESHOLD * 100)
        warning_pct = int(self.scorer.WARNING_THRESHOLD * 100)

        worksheet.write(row, 0, "Legend", formats["legend_label"])

        worksheet.write(row + 1, 0, "Good", formats["legend_good"])
        worksheet.write(row + 1, 1, f"Score ≥ {good_pct}%")

        worksheet.write(row + 2, 0, "Warning", formats["legend_warning"])
        worksheet.write(row + 2, 1, f"Score {warning_pct}% – {good_pct - 1}%")

        worksheet.write(row + 3, 0, "Poor", formats["legend_poor"])
        worksheet.write(row + 3, 1, f"Score < {warning_pct}%")

    @staticmethod
    def _format_timestamp(run_timestamp: str) -> str:
        try:
            return datetime.fromisoformat(run_timestamp).strftime("%d-%b-%Y %H:%M")
        except (TypeError, ValueError):
            return str(run_timestamp)

    @staticmethod
    def _row_format(status: str, formats: dict[str, Any]) -> Any:
        if status == "good":
            return formats["row_good"]

        if status == "warning":
            return formats["row_warning"]

        return formats["row_poor"]

    @staticmethod
    def _overall_format(status: str, formats: dict[str, Any]) -> Any:
        if status == "good":
            return formats["overall_good"]

        if status == "warning":
            return formats["overall_warning"]

        return formats["overall_poor"]
