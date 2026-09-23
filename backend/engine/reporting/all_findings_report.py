"""Builds and writes the All DQ Findings sheet: one row per rule execution detail across every table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import xlsxwriter
from pyspark.sql import DataFrame
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from engine.core.result_models import (
    RuleExecutionDetail,
    ValidationRunResult,
)
from engine.core.spark_session import get_spark_session
from engine.reporting.all_findings_workbook_writer import (
    AllFindingsWorkbookWriter,
)
from engine.reporting.dimension_scorer import DimensionScorer
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS
from utils.logger import get_logger


logger = get_logger(__name__)


class AllFindingsReport:
    """Flattens every table's rule execution details into the All DQ Findings sheet."""

    SHEET_NAME = "All DQ Findings"

    COLUMNS = [
        "#",
        "Table",
        "Column",
        "CDE",
        "Dimension",
        "Rule ID",
        "Rule Notes",
        "Invalid Count",
        "Total Rows",
        "Pass Count",
        "Score",
    ]

    SCHEMA = StructType(
        [
            StructField("#", IntegerType(), False),
            StructField("Table", StringType(), True),
            StructField("Column", StringType(), True),
            StructField("CDE", StringType(), True),
            StructField("Dimension", StringType(), True),
            StructField("Rule ID", StringType(), True),
            StructField("Rule Notes", StringType(), True),
            StructField("Invalid Count", IntegerType(), False),
            StructField("Total Rows", IntegerType(), False),
            StructField("Pass Count", IntegerType(), False),
            StructField("Score", DoubleType(), False),
        ]
    )

    def __init__(
        self,
        scorer: DimensionScorer | None = None,
        workbook_writer: AllFindingsWorkbookWriter | None = None,
    ) -> None:
        """Store the scorer and workbook writer collaborators."""
        self.scorer = scorer or DimensionScorer()
        self.workbook_writer = (
            workbook_writer
            or AllFindingsWorkbookWriter(scorer=self.scorer)
        )

    def build(
        self,
        validation_result: ValidationRunResult,
    ) -> DataFrame:
        """Build one row per rule execution detail across every table."""
        try:
            rows: list[dict[str, Any]] = []

            index = 1

            for table_result in (
                validation_result.tables.values()
            ):
                for detail in table_result.rule_details:
                    rows.append(
                        self._detail_to_row(
                            index=index,
                            detail=detail,
                        )
                    )
                    index += 1

            dataframe = get_spark_session().createDataFrame(
                rows,
                schema=self.SCHEMA,
            )

            # len(rows) - the Python list already built above - instead of dataframe.count(),
            # which would otherwise force a Spark action just to log a number already known.
            logger.debug(
                "Built All DQ Findings report with %s rows",
                len(rows),
            )

            return dataframe

        except Exception:
            logger.exception(
                "Failed to build All DQ Findings report"
            )
            raise

    def write(
        self,
        validation_result: ValidationRunResult,
        output_path: str | Path,
        sheet_name: str = SHEET_NAME,
    ) -> Path:
        """Write the All DQ Findings sheet to a standalone workbook."""
        output_path = Path(
            output_path
        )

        try:
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            dataframe = self.build(
                validation_result
            )

            with xlsxwriter.Workbook(str(output_path), XLSXWRITER_SAFE_OPTIONS) as workbook:
                # write_to_workbook() collect()s `dataframe` to render it - reuse the row
                # count it already computed instead of counting a second time here.
                row_count = self.write_to_workbook(
                    writer=workbook,
                    dataframe=dataframe,
                    sheet_name=sheet_name,
                )

            logger.info(
                "Wrote All DQ Findings report with %s rows to '%s'",
                row_count,
                output_path,
            )

            return output_path

        except Exception:
            logger.exception(
                "Failed to write All DQ Findings report '%s'",
                output_path,
            )
            raise

    def write_to_workbook(
        self,
        writer: Any,
        dataframe: DataFrame,
        sheet_name: str = SHEET_NAME,
    ) -> int:
        """Add the All DQ Findings worksheet, delegate its formatting, and return the row count written."""
        try:
            workbook = getattr(writer, "book", writer)
            worksheet = workbook.add_worksheet(sheet_name)

            row_count = self.workbook_writer.write(
                workbook=workbook,
                worksheet=worksheet,
                dataframe=dataframe,
            )

            logger.debug(
                "Wrote All DQ Findings sheet '%s'",
                sheet_name,
            )

            return row_count

        except Exception:
            logger.exception(
                "Failed to write All DQ Findings sheet '%s'",
                sheet_name,
            )
            raise

    @staticmethod
    def _detail_to_row(
        index: int,
        detail: RuleExecutionDetail,
    ) -> dict[str, Any]:
        """Convert one rule execution detail into a report row dict."""

        return {
            "#": index,
            "Table": detail.table_name,
            "Column": detail.column_name,
            "CDE": (
                "X"
                if detail.cde
                else ""
            ),
            "Dimension": detail.dimension,
            "Rule ID": detail.rule_id,
            "Rule Notes": detail.rule_notes,
            "Invalid Count": detail.invalid_count,
            "Total Rows": detail.total_rows,
            "Pass Count": detail.pass_count,
            "Score": detail.score,
        }
