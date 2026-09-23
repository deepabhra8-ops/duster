from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from engine.core.result_models import RuleExecutionDetail, ValidationRunResult


SHEET_DIMENSIONS = (
    "Completeness",
    "Conformity",
    "Uniqueness",
)


def empty_summary() -> dict[str, Any]:
    return {
        "overall_score": None,
        "dimensions": {},
        "tables": [],
        "findings": [],
        "not_run_count": 0,
        "sheets": {
            **{name: [] for name in SHEET_DIMENSIONS},
            "All Findings": [],
        },
    }


def build_summary(
    validation_result: "ValidationRunResult | None",
) -> dict[str, Any]:
    if validation_result is None:
        return empty_summary()

    findings: list[dict[str, Any]] = []
    table_groups: dict[str, dict[str, Any]] = {}
    
    sheets: dict[str, list[dict[str, Any]]] = {
        name: [] for name in SHEET_DIMENSIONS
    }
    sheets["All Findings"] = []

    not_run_count = 0

    for table_name, table_result in validation_result.tables.items():
        for detail in table_result.rule_details:
            if not detail.was_run:
                not_run_count += 1

            findings.append(_finding_row(table_name, detail))

            row = _sheet_row(table_name, detail)
            sheets["All Findings"].append(row)

            if detail.dimension in SHEET_DIMENSIONS:
                sheets[detail.dimension].append(row)

            group = table_groups.setdefault(
                table_name,
                {"name": table_name, "total": 0, "fail": 0, "pass": 0},
            )
            group["total"] += detail.total_rows
            group["fail"] += detail.invalid_count
            group["pass"] += detail.pass_count


    dimensions = {
        name: round(result.score, 4)
        for name, result in validation_result.summary.dimension_results.items()
    }

    overall_score = (
        round(validation_result.overall_score, 4)
        if dimensions
        else None
    )

    return {
        "overall_score": overall_score,
        "dimensions": dimensions,
        "tables": list(table_groups.values()),
        "findings": findings,
        "sheets": sheets,
        "not_run_count": not_run_count,
    }


def _finding_row(
    table_name: str,
    detail: "RuleExecutionDetail",
) -> dict[str, Any]:
    return {
        "table": table_name,
        "column": detail.column_name,
        "rule": detail.rule_id,
        "dimension": detail.dimension,
        "invalid": detail.invalid_count,
        "total": detail.total_rows,
        "score": round(detail.score, 4) if detail.was_run else None,
        "status": detail.status,
    }


def _sheet_row(
    table_name: str,
    detail: "RuleExecutionDetail",
) -> dict[str, Any]:
    return {
        "table": table_name,
        "column": detail.column_name,
        "cde": bool(detail.cde),
        "ruleId": detail.rule_id,
        "ruleNotes": detail.rule_notes,
        "invalidCount": detail.invalid_count,
        "totalCount": detail.total_rows,
        "score": round(detail.score, 4) if detail.was_run else None,
        "status": detail.status,
    }



