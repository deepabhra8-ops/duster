from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter

from engine.core.result_models import ValidationRunResult
from engine.reporting.all_findings_report import (
    AllFindingsReport,
)
from engine.reporting.dimension_report import (
    DimensionReport,
)
from engine.reporting.failed_rows_report import (
    FailedRowsReport,
)
from engine.reporting.summary_report import (
    SummaryReport,
)
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger, log_and_reraise


logger = get_logger(__name__)


class ReportBuilder:
    SUMMARY_SHEET = "Summary"
    ALL_FINDINGS_SHEET = "All DQ Findings"
    FAILED_ROWS_SHEET = "Failed Rows"

    @log_and_reraise(logger, "Failed to initialize report builder")
    def __init__(
        self,
        summary_report: SummaryReport | None = None,
        dimension_report: DimensionReport | None = None,
        all_findings_report: AllFindingsReport | None = None,
        failed_rows_report: FailedRowsReport | None = None,
    ) -> None:
        self.summary_report = (
            summary_report
            or SummaryReport()
        )

        self.dimension_report = (
            dimension_report
            or DimensionReport()
        )

        self.all_findings_report = (
            all_findings_report
            or AllFindingsReport()
        )

        self.failed_rows_report = (
            failed_rows_report
            or FailedRowsReport()
        )

        logger.debug("Initialized report builder")

    @log_and_reraise(logger, "Failed to build reports")
    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> dict[str, pl.DataFrame]:
        reports: dict[
            str,
            pl.DataFrame,
        ] = {}

        reports[
            self.SUMMARY_SHEET
        ] = self.summary_report.build(
            validation_result
        )

        dimension_reports = (
            self.dimension_report.build(
                validation_result
            )
        )

        if isinstance(
            dimension_reports,
            dict,
        ):
            reports.update(
                dimension_reports
            )
        else:
            reports[
                "Dimension Summary"
            ] = dimension_reports

        reports[
            self.ALL_FINDINGS_SHEET
        ] = self.all_findings_report.build(
            validation_result
        )

        reports[
            self.FAILED_ROWS_SHEET
        ] = self.failed_rows_report.build(
            validation_result
        )

        logger.debug(
            "Built %s report sheets",
            len(reports),
        )

        return reports

    @log_and_reraise(
        logger,
        lambda self, validation_result, output_path, **_: (
            "Failed to write reports to '%s'",
            output_path,
        ),
    )
    def write(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
    ) -> Path:
        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with xlsxwriter.Workbook(
            str(output_path),
            XLSXWRITER_SAFE_OPTIONS,
        ) as writer:

            self._write_summary(
                writer=writer,
                validation_result=validation_result,
            )

            self._write_dimensions(
                writer=writer,
                validation_result=validation_result,
            )

            self._write_all_findings(
                writer=writer,
                validation_result=validation_result,
            )

            self._write_failed_rows(
                writer=writer,
                validation_result=validation_result,
            )

        logger.info(
            "Wrote validation report to '%s'",
            output_path,
        )

        return output_path

    @log_and_reraise(
        logger,
        lambda self, validation_result, output_path, sheet_name, **_: (
            "Failed to write report sheet '%s' to '%s'",
            sheet_name,
            output_path,
        ),
    )
    def write_sheet(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
        sheet_name: str,
    ) -> Path:
        output_path = Path(
            output_path
        )

        available_sheets = self._available_sheet_names(
            validation_result
        )

        if sheet_name not in available_sheets:
            raise KeyError(
                f"Unknown report sheet: {sheet_name}. "
                f"Available sheets: "
                f"{', '.join(available_sheets)}"
            )

        with xlsxwriter.Workbook(
            str(output_path),
            XLSXWRITER_SAFE_OPTIONS,
        ) as writer:

            if sheet_name == self.SUMMARY_SHEET:

                self._write_summary(
                    writer=writer,
                    validation_result=validation_result,
                )

            elif sheet_name == self.ALL_FINDINGS_SHEET:

                self._write_all_findings(
                    writer=writer,
                    validation_result=validation_result,
                )

            elif sheet_name == self.FAILED_ROWS_SHEET:

                self._write_failed_rows(
                    writer=writer,
                    validation_result=validation_result,
                )

            else:

                self._write_dimension(
                    writer=writer,
                    validation_result=validation_result,
                    sheet_name=sheet_name,
                )

        logger.info(
            "Wrote report sheet '%s' to '%s'",
            sheet_name,
            output_path,
        )

        return output_path

    def _write_summary(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
    ) -> None:
        self.summary_report.write_to_workbook(
            writer=writer,
            validation_result=validation_result,
            sheet_name=self.SUMMARY_SHEET,
        )

    def _write_dimensions(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
    ) -> None:
        dimension_reports = (
            self.dimension_report.build(
                validation_result
            )
        )

        if not isinstance(
            dimension_reports,
            dict,
        ):
            self.dimension_report.write_to_workbook(
                writer=writer,
                dataframe=dimension_reports,
                sheet_name="Dimension Summary",
                dimension="Dimension Summary",
            )
            return

        for (
            sheet_name,
            dataframe,
        ) in dimension_reports.items():

            dimension = (
                self._dimension_from_sheet_name(
                    sheet_name
                )
            )

            self.dimension_report.write_to_workbook(
                writer=writer,
                dataframe=dataframe,
                sheet_name=sheet_name,
                dimension=dimension,
            )

    def _write_dimension(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
        sheet_name: str,
    ) -> None:
        dimension = (
            self._dimension_from_sheet_name(
                sheet_name
            )
        )

        dataframe = (
            self.dimension_report.build_dimension(
                validation_result=validation_result,
                dimension=dimension,
            )
        )

        self.dimension_report.write_to_workbook(
            writer=writer,
            dataframe=dataframe,
            sheet_name=sheet_name,
            dimension=dimension,
        )

    def _write_all_findings(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
    ) -> None:
        dataframe = (
            self.all_findings_report.build(
                validation_result
            )
        )

        self.all_findings_report.write_to_workbook(
            writer=writer,
            dataframe=dataframe,
            sheet_name=self.ALL_FINDINGS_SHEET,
        )

    def _write_failed_rows(
        self,
        writer: Any,
        validation_result: ValidationRunResult,
    ) -> None:
        self.failed_rows_report.write_to_workbook(
            writer=writer,
            validation_result=validation_result,
            sheet_name=self.FAILED_ROWS_SHEET,
        )

    def _available_sheet_names(
        self,
        validation_result: ValidationRunResult,
    ) -> list[str]:
        dimension_reports = self.dimension_report.build(
            validation_result
        )

        sheet_names = [self.SUMMARY_SHEET]

        if isinstance(dimension_reports, dict):
            sheet_names.extend(dimension_reports.keys())
        else:
            sheet_names.append("Dimension Summary")

        sheet_names.append(self.ALL_FINDINGS_SHEET)
        sheet_names.append(self.FAILED_ROWS_SHEET)

        return sheet_names

    @staticmethod
    def _dimension_from_sheet_name(
        sheet_name: str,
    ) -> str:
        return str(
            sheet_name
        ).strip()
