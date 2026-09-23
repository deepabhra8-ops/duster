"""Converts a profile map into the flat JSON rows the UI renders and the API stores.

Lives in the engine because it reads TableRuleConfiguration/RuleConfiguration, the
engine's own result types. Glue calls this the moment profiling finishes and writes
the result straight to Postgres; the web app only ever handles the resulting JSON.

Row keys are the literal workbook headers (minus the leading "#", which is display
numbering derived from array position) so a stored row and an exported worksheet row
are the same shape.
"""

from __future__ import annotations

from typing import Any, Mapping

from engine.core.result_models import TableRuleConfiguration


COLUMNS = (
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
    "CDE (X=Yes)",
    "Applicable Rules",
    "Rule Parameters",
    "Analyst Notes",
)


def build_rows(
    tables: Mapping[str, TableRuleConfiguration],
) -> list[dict[str, Any]]:
    """Turn a profile map (one TableRuleConfiguration per table) into flat JSON rows.

    One row per profiled column across every table. Reads the snake_case metadata
    keys ProfileMapBuilder produces (dtype/total_count/null_count/distinct_count/
    min_value/max_value) - this path never goes through Excel, so there are no
    capitalized sheet headers to read here.

    "Null %" and "Unique %" aren't stored anywhere; they're derived the same way the
    workbook writer derives them, so both outputs always agree.
    """
    rows: list[dict[str, Any]] = []

    for table_name, configuration in tables.items():
        for column in configuration.columns:
            metadata = column.metadata or {}

            total_count = metadata.get("total_count", 0)
            null_count = metadata.get("null_count", 0)
            distinct_count = metadata.get("distinct_count", 0)

            rows.append(
                {
                    "Row ID": "",
                    "Enabled": "Y",
                    "Table": table_name,
                    "Column": column.column_name,
                    "Data Type": _stringify(metadata.get("dtype")),
                    "Total Count": _stringify(total_count),
                    "Null Count": _stringify(null_count),
                    "Null %": _percentage(null_count, total_count),
                    "Distinct Count": _stringify(distinct_count),
                    "Unique %": _percentage(distinct_count, total_count),
                    "Min Value": _stringify(metadata.get("min_value")),
                    "Max Value": _stringify(metadata.get("max_value")),
                    "CDE (X=Yes)": "X" if column.cde else "",
                    "Applicable Rules": ", ".join(column.rule_ids),
                    "Rule Parameters": column.parameters or "",
                    "Analyst Notes": column.analyst_notes or "",
                }
            )

    return rows


def _stringify(value: Any) -> str:
    """Render a metadata value as a string, with None becoming empty."""
    if value is None:
        return ""

    return str(value)


def _percentage(part: Any, total: Any) -> str:
    """Format part/total as a percentage string, guarding zero/invalid totals."""
    try:
        part = float(part)
        total = float(total)
    except (TypeError, ValueError):
        return "0.00%"

    if not total:
        return "0.00%"

    return f"{round((part / total) * 100, 2):.2f}%"
