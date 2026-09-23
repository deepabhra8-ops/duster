"""Writes profile-map rule configuration to an Excel workbook (one formatted sheet per table plus an instructions sheet)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import polars as pl
import xlsxwriter

from engine.core.result_models import TableRuleConfiguration
from common.files.excel_safety import XLSXWRITER_SAFE_OPTIONS, is_missing
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfileMapWriter:
    """Writes TableRuleConfiguration data to a formatted profile-map Excel workbook."""

    CDE_HEADER = "CDE\n(X=Yes)"
    RULES_HEADER = "Applicable Rule\n(Single ID)"
    PARAMETERS_HEADER = "Rule Parameters\n(see Instructions)"

    COLUMNS = [
        "#",
        "Row ID",
        "Enabled",
        "Table",
        "Column",
        "Data Type",
        "Total Count",
        "Null Count",
        "Null %",
        "Distinct Count",
        "Unique %",
        "Min Value",
        "Max Value",
        CDE_HEADER,
        RULES_HEADER,
        PARAMETERS_HEADER,
        "Analyst Notes",
    ]

    def write(
        self,
        profile_map: Mapping[str, TableRuleConfiguration],
        path: str | Path,
        project_name: str = "Project",
        run_timestamp: str | None = None,
    ) -> Path:
        """Write the full profile map workbook (instructions sheet plus one sheet per table)."""
        path = Path(path)

        try:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            # xlsxwriter directly: this writer already styles every header and
            # column itself, so a dataframe library's Excel wrapper was only
            # writing the data rows.
            with xlsxwriter.Workbook(
                str(path),
                XLSXWRITER_SAFE_OPTIONS,
            ) as writer:
                self._write_instructions(
                    writer=writer,
                    project_name=project_name,
                    run_timestamp=run_timestamp,
                )

                self._used_sheet_names = {"Instructions"}

                for table_name, configuration in profile_map.items():
                    self._write_table(
                        writer=writer,
                        table_name=table_name,
                        configuration=configuration,
                    )

            logger.info(
                "Wrote profile map '%s' with %s table configurations",
                path,
                len(profile_map),
            )
            return path
        except Exception:
            logger.exception("Failed to write profile map '%s'", path)
            raise

    def _write_instructions(
        self,
        writer: Any,
        project_name: str,
        run_timestamp: str | None,
    ) -> None:
        """Write the Instructions sheet explaining how to fill in the profile map."""
        try:
            workbook = getattr(writer, "book", writer)
            worksheet = workbook.add_worksheet("Instructions")

            worksheet.set_column("A:A", 20)
            worksheet.set_column("B:B", 80)

            label_format = workbook.add_format(
                {
                    "bold": True,
                }
            )

            generated = self._format_generated(
                run_timestamp
            )

            rows = [
                (
                    "Document",
                    f"{project_name} – Source DQ Profile Map",
                ),
                ("Generated", generated),
                (
                    "Step",
                    "Step 1 output – review and update before "
                    "running DQ Validator",
                ),
                ("", ""),
                (
                    "How to use",
                    "1. Review each table sheet below.",
                ),
                (
                    "",
                    "2. Set CDE = 'X' for Critical Data Elements.",
                ),
                (
                    "",
                    "3. Adjust 'Applicable Rule' – one rule ID per row.",
                ),
                (
                    "",
                    "4. Fill in 'Rule Parameters' for each rule per "
                    "column.",
                ),
                (
                    "",
                    "5. Save and pass this file to the DQ Validator "
                    "(Step 3).",
                ),
            ]

            for row_index, (label, value) in enumerate(rows):
                worksheet.write(
                    row_index,
                    0,
                    label,
                    label_format,
                )

                worksheet.write(
                    row_index,
                    1,
                    value,
                )
        except Exception:
            logger.exception("Failed to write profile-map instructions")
            raise

    @staticmethod
    def _format_generated(
        run_timestamp: str | None,
    ) -> str:
        """Format the run timestamp for display, falling back to now."""
        if run_timestamp:
            try:
                return datetime.fromisoformat(
                    run_timestamp
                ).strftime("%d-%b-%Y %H:%M:%S")
            except ValueError:
                return run_timestamp

        return datetime.now().strftime("%d-%b-%Y %H:%M:%S")

    def _write_table(
        self,
        writer: Any,
        table_name: str,
        configuration: TableRuleConfiguration,
    ) -> None:
        """Write one table's rule configuration as a formatted sheet."""
        try:
            rows: list[dict[str, Any]] = []

            for index, column in enumerate(
                configuration.columns,
                start=1,
            ):
                metadata = dict(
                    column.metadata
                )

                total_count = metadata.get(
                    "total_count",
                    0,
                )

                null_count = metadata.get(
                    "null_count",
                    0,
                )

                distinct_count = metadata.get(
                    "distinct_count",
                    0,
                )

                rows.append(
                    {
                        "#": index,
                        "Row ID": "",
                        "Enabled": "Y",
                        "Table": table_name,
                        "Column": column.column_name,
                        "Data Type": metadata.get(
                            "dtype",
                            "",
                        ),
                        "Total Count": total_count,
                        "Null Count": null_count,
                        "Null %": self._percentage(
                            null_count,
                            total_count,
                        ),
                        "Distinct Count": distinct_count,
                        "Unique %": self._percentage(
                            distinct_count,
                            total_count,
                        ),
                        "Min Value": self._stringify(
                            metadata.get("min_value")
                        ),
                        "Max Value": self._stringify(
                            metadata.get("max_value")
                        ),
                        self.CDE_HEADER: (
                            "X"
                            if column.cde
                            else ""
                        ),
                        self.RULES_HEADER: ", ".join(
                            column.rule_ids
                        ),
                        self.PARAMETERS_HEADER: column.parameters,
                        "Analyst Notes": column.analyst_notes,
                    }
                )

            dataframe = (
                pl.DataFrame(rows).select(self.COLUMNS)
                if rows
                else pl.DataFrame(schema={name: pl.Utf8 for name in self.COLUMNS})
            )

            safe_sheet_name = self._safe_sheet_name(
                table_name
            )

            workbook = getattr(writer, "book", writer)
            worksheet = workbook.add_worksheet(safe_sheet_name)

            # Data starts at row 1; _format_table writes the styled header into
            # row 0 immediately after.
            for row_index, record in enumerate(dataframe.iter_rows(), start=1):
                for column_index, value in enumerate(record):
                    worksheet.write(
                        row_index,
                        column_index,
                        "" if is_missing(value) else value,
                    )

            self._format_table(
                workbook=workbook,
                worksheet=worksheet,
                dataframe=dataframe,
            )
        except Exception:
            logger.exception(
                "Failed to write profile-map table '%s'",
                table_name,
            )
            raise

    @staticmethod
    def _stringify(value: Any) -> str:
        """Render a min/max metadata value as text, with None becoming empty.

        Min/Max is the one column that genuinely mixes types across rows: a date or
        numeric column yields a real value, while a string or boolean one yields the
        NOT_APPLICABLE sentinel. Handing that mixture to pl.DataFrame() below raises
        ComputeError ("could not append value ... of type datetime[us] to the
        builder"), so any table with both a temporal and a text column would fail to
        write at all.

        Mirrors profile_map_rows._stringify deliberately: that is what the Glue path
        already stores for these two fields, so a workbook written here and the rows
        stored from a Glue run stay identical rather than drifting apart.
        """
        if value is None:
            return ""

        return str(value)

    @staticmethod
    def _percentage(
        part: Any,
        total: Any,
    ) -> str:
        """Format part/total as a percentage string, guarding against zero/invalid totals."""
        try:
            part = float(part)
            total = float(total)
        except (TypeError, ValueError):
            return "0.00%"

        if not total:
            return "0.00%"

        return f"{round((part / total) * 100, 2):.2f}%"

    def _format_table(
        self,
        workbook: Any,
        worksheet: Any,
        dataframe: pl.DataFrame,
    ) -> None:
        """Apply header styling, column widths, freeze panes, and autofilter to a sheet."""

        header_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        )

        editable_format = workbook.add_format(
            {
                "border": 1,
            }
        )

        for column_index, column_name in enumerate(
            dataframe.columns
        ):
            worksheet.write(
                0,
                column_index,
                column_name,
                header_format,
            )

        for column_index, column_name in enumerate(
            dataframe.columns
        ):
            width = max(
                len(str(column_name)) + 2,
                12,
            )

            if not dataframe.is_empty():
                max_value_length = max(
                    (
                        len(str(value))
                        for value in dataframe[column_name]
                        if not is_missing(value)
                    ),
                    default=0,
                )

                if max_value_length:
                    width = max(
                        width,
                        max_value_length + 2,
                    )

            worksheet.set_column(
                column_index,
                column_index,
                min(width, 50),
                editable_format,
            )

        worksheet.freeze_panes(
            1,
            0,
        )

        worksheet.autofilter(
            0,
            0,
            max(len(dataframe), 1),
            len(dataframe.columns) - 1,
        )

    def _safe_sheet_name(
        self,
        table_name: str,
    ) -> str:
        """Sanitize a table name into a valid, length-limited, unique Excel sheet name."""
        invalid_characters = {
            "[",
            "]",
            ":",
            "*",
            "?",
            "/",
            "\\",
        }

        sheet_name = str(table_name).strip()

        for character in invalid_characters:
            sheet_name = sheet_name.replace(
                character,
                "_",
            )

        if not sheet_name:
            sheet_name = "Table"

        base_name = sheet_name
        suffix = 1
        proposed = base_name[:31]

        used = getattr(self, "_used_sheet_names", set())
        
        while proposed.lower() in {name.lower() for name in used}:
            suffix_str = f"_{suffix}"
            max_base_len = 31 - len(suffix_str)
            proposed = base_name[:max_base_len] + suffix_str
            suffix += 1

        used.add(proposed)
        self._used_sheet_names = used
        
        return proposed
