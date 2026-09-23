"""Builds the JSON summary of a validation run: scores, per-dimension rollups, findings.

Lives in the engine because it reads ValidationRunResult/RuleExecutionDetail. Glue
builds this the moment validation finishes and writes it to Postgres, so the web app
serves a stored summary instead of re-parsing the report workbook - a re-parse that
never worked on AWS anyway, where report_path is a bare S3 key.

DimensionResult/ValidationSummary already average per-rule scores per dimension and
per-dimension scores overall. The one intentional divergence: an empty run's
ValidationSummary defaults overall_score to 1.0, which would read as a perfect score
for a job that validated nothing - None is used here instead, which is what the UI
treats as "no data yet".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from engine.core.result_models import RuleExecutionDetail, ValidationRunResult


# The dimensions with their own gauge and tab in the UI. A finding in another
# dimension (e.g. a Consistency or Custom rule) still lands in "All Findings" and
# still counts toward the dimension rollup and overall score - it just has no
# dedicated tab.
SHEET_DIMENSIONS = (
    "Completeness",
    "Conformity",
    "Uniqueness",
)


def empty_summary() -> dict[str, Any]:
    """The summary shape for a job with no validation results yet."""
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
    """Build the full job summary from a ValidationRunResult. No file I/O."""
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
        # How many configured checks could not be performed. Surfaced next to
        # the score so a run whose score looks fine is not mistaken for a run
        # that actually checked everything.
        "not_run_count": not_run_count,
    }


def _finding_row(
    table_name: str,
    detail: "RuleExecutionDetail",
) -> dict[str, Any]:
    """RuleExecutionDetail -> the flat findings row the results table renders."""
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
    """RuleExecutionDetail -> the camelCase row shape the sheet grid expects.

    A check that could not run carries score None rather than a number. Its
    underlying score is 1.0 by construction (an all-pass mask), and rendering
    that as "100%" is precisely the misreport this exists to prevent - the grid
    shows a NOT RUN badge instead.
    """
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



