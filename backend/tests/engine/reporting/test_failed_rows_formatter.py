from __future__ import annotations

from engine.core.result_models import RowFailure
from engine.reporting.failed_rows_formatter import FailedRowsFormatter


def _failure(rule_id: str, column_name: str = "col") -> RowFailure:
    return RowFailure(
        column_name=column_name,
        rule_id=rule_id,
        notes="some note",
        dimension="Completeness",
        category="Nulls",
    )


def test_reference_string_renders_one_line_per_failure():
    failures = [_failure("DQ1", "name"), _failure("DQ5", "age")]

    result = FailedRowsFormatter().reference_string(failures)

    assert result == (
        "DQ1 - Completeness - Nulls - name\n"
        "DQ5 - Completeness - Nulls - age"
    )


def test_reference_string_is_empty_for_no_failures():
    assert FailedRowsFormatter().reference_string([]) == ""


def test_sort_failures_orders_rules_numerically_not_lexically():
    failures = [_failure("DQ10", "a"), _failure("DQ2", "b"), _failure("DQ9", "c")]

    sorted_failures = FailedRowsFormatter().sort_failures(failures)

    assert [failure.rule_id for failure in sorted_failures] == ["DQ2", "DQ9", "DQ10"]


def test_sort_failures_breaks_ties_on_column_name():
    failures = [_failure("DQ1", "zebra"), _failure("DQ1", "apple")]

    sorted_failures = FailedRowsFormatter().sort_failures(failures)

    assert [failure.column_name for failure in sorted_failures] == ["apple", "zebra"]


def test_sort_failures_puts_unrecognized_rule_ids_last():
    failures = [_failure("CUSTOM_RULE", "a"), _failure("DQ1", "b")]

    sorted_failures = FailedRowsFormatter().sort_failures(failures)

    assert [failure.rule_id for failure in sorted_failures] == ["DQ1", "CUSTOM_RULE"]
