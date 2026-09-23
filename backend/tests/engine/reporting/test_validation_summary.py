"""Unit tests for the validation summary the job runner stores and the UI renders.

Built from a ValidationRunResult with no file I/O - this is what replaced
re-parsing the report workbook on every request.
"""
from __future__ import annotations

from engine.core.result_models import (
    DimensionResult,
    RowFailure,
    RuleExecutionDetail,
    TableValidationResult,
    ValidationRunResult,
    ValidationSummary,
)
from engine.reporting.validation_summary import (
    build_summary,
    empty_summary,
)


def _detail(rule_id="DQ1", dimension="Completeness", invalid=5, total=100, cde=True):
    return RuleExecutionDetail(
        table_name="claim",
        column_name="claim_id",
        rule_id=rule_id,
        dimension=dimension,
        cde=cde,
        rule_notes="Value must not be null",
        total_rows=total,
        invalid_count=invalid,
        pass_count=total - invalid,
        score=(total - invalid) / total,
    )


def _run_result(details, row_failures=None):
    # row_failures is deliberately built as the mapping TableValidator actually
    # produces - {row id: [RowFailure, ...]} - not a flat list. An earlier version
    # of this helper passed a list, which made build_summary()'s own iteration bug
    # invisible: over a list it read RowFailure objects, over the real mapping it
    # read bare row ids and produced blank entries.
    table = TableValidationResult(
        table_name="claim",
        total_rows=100,
        pass_mask=None,
        rule_details=list(details),
        row_failures=dict(row_failures or {}),
    )

    dimensions = {}
    for detail in details:
        dimensions.setdefault(detail.dimension, []).append(detail.score)

    dimension_results = {
        name: DimensionResult.from_scores(dimension=name, scores=scores)
        for name, scores in dimensions.items()
    }

    return ValidationRunResult(
        project_name="test",
        run_timestamp="2026-01-01T00:00:00",
        summary=ValidationSummary.from_dimensions(dimension_results=dimension_results),
        tables={"claim": table},
    )


def test_empty_summary_scores_none_not_one():
    """A run that validated nothing must not read as a perfect score."""
    summary = empty_summary()

    assert summary["overall_score"] is None
    assert summary["dimensions"] == {}


def test_build_summary_of_none_is_empty():
    assert build_summary(None) == empty_summary()


def test_findings_and_scores():
    summary = build_summary(_run_result([_detail(invalid=5, total=100)]))

    assert summary["overall_score"] == 0.95
    assert summary["dimensions"]["Completeness"] == 0.95

    finding = summary["findings"][0]
    assert finding["table"] == "claim"
    assert finding["column"] == "claim_id"
    assert finding["rule"] == "DQ1"
    assert finding["invalid"] == 5
    assert finding["total"] == 100


def test_table_rollup_totals():
    summary = build_summary(
        _run_result([_detail(invalid=5), _detail(rule_id="DQ10", dimension="Uniqueness", invalid=1)])
    )

    table = summary["tables"][0]
    assert table["name"] == "claim"
    assert table["total"] == 200
    assert table["fail"] == 6
    assert table["pass"] == 194


def test_rows_land_in_their_dimension_tab_and_all_findings():
    summary = build_summary(
        _run_result([_detail(dimension="Completeness"), _detail(rule_id="DQ10", dimension="Uniqueness")])
    )

    assert len(summary["sheets"]["All Findings"]) == 2
    assert len(summary["sheets"]["Completeness"]) == 1
    assert len(summary["sheets"]["Uniqueness"]) == 1
    assert summary["sheets"]["Conformity"] == []


def test_finding_outside_the_tabbed_dimensions_still_counts():
    """A Consistency rule has no tab but must still reach All Findings and the score."""
    summary = build_summary(
        _run_result([_detail(rule_id="DQ9", dimension="Consistency", invalid=10)])
    )

    assert len(summary["sheets"]["All Findings"]) == 1
    assert "Consistency" in summary["dimensions"]
    assert summary["overall_score"] == 0.9


def test_sheet_rows_use_camel_case_keys():
    row = build_summary(_run_result([_detail()]))["sheets"]["All Findings"][0]

    assert set(row) == {
        "table",
        "column",
        "cde",
        "ruleId",
        "ruleNotes",
        "invalidCount",
        "totalCount",
        "score",
        "status",
    }
    assert row["cde"] is True


# ── Checks that could not run ────────────────────────────────────────
# A rule that could not be performed (no reference list, no configured columns,
# an unparseable expression, an internal error) carries an all-pass mask, so its
# raw score is 1.0. Reporting that as 100% told customers a check had passed
# when it had never executed. These assert it is surfaced as NOT RUN instead.


def _not_run_detail(rule_id="DQ8", dimension="Conformity", reason="Reference list not found"):
    return RuleExecutionDetail(
        table_name="claim",
        column_name="claim_id",
        rule_id=rule_id,
        dimension=dimension,
        cde=True,
        rule_notes=reason,
        total_rows=100,
        invalid_count=0,
        pass_count=100,
        score=1.0,
        metadata={"status": "not_run", "not_run_reason": reason},
    )


def test_a_not_run_check_reports_no_score():
    row = build_summary(_run_result([_not_run_detail()]))["sheets"]["All Findings"][0]

    assert row["score"] is None
    assert row["status"] == "not_run"


def test_a_normal_check_still_reports_ok_and_a_number():
    row = build_summary(_run_result([_detail()]))["sheets"]["All Findings"][0]

    assert row["score"] == 0.95
    assert row["status"] == "ok"


def test_not_run_checks_are_counted():
    summary = build_summary(
        _run_result([_detail(), _not_run_detail(), _not_run_detail(rule_id="DQ9")])
    )

    assert summary["not_run_count"] == 2


def test_findings_row_also_carries_status_and_null_score():
    finding = build_summary(_run_result([_not_run_detail()]))["findings"][0]

    assert finding["score"] is None
    assert finding["status"] == "not_run"


def test_a_detail_without_a_status_key_is_treated_as_ok():
    """Results produced by an engine build predating the status key must not
    suddenly render as NOT RUN."""
    legacy = _detail()

    assert legacy.metadata == {}

    row = build_summary(_run_result([legacy]))["sheets"]["All Findings"][0]

    assert row["status"] == "ok"
    assert row["score"] == 0.95


