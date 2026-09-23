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
    if value is None:
        return ""

    return str(value)


def _percentage(part: Any, total: Any) -> str:
    try:
        part = float(part)
        total = float(total)
    except (TypeError, ValueError):
        return "0.00%"

    if not total:
        return "0.00%"

    return f"{round((part / total) * 100, 2):.2f}%"
