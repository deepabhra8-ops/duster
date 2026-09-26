from __future__ import annotations

from typing import Any

from engine.quality.models import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_NO_DATA,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_WARN,
    ResultRecord,
    RuleInstance,
)
from engine.quality.planner import Binding, Skip
from engine.quality.rule_loader import effective_dimension
from engine.quality.templates import RuleTemplate


MAX_MESSAGE_LENGTH = 2000


def short_error(exc: BaseException | str) -> str:
    """Spark and Py4J errors carry query plans and JVM stack traces; keep the one line
    a person can act on."""
    text = str(exc).strip()

    for line in text.splitlines():
        line = line.strip().lstrip(":").strip()

        if not line or line.startswith("An error occurred while calling") or line.startswith("at "):
            continue

        return line[:500]

    return (text or type(exc).__name__)[:500]


def record_for(
    rule: RuleInstance,
    template: RuleTemplate,
    status: str,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    table: str | None = None,
    column: str | None = None,
    **fields: Any,
) -> ResultRecord:
    message = fields.pop("message", None)

    return ResultRecord(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        rule_version=rule.version,
        template=template.name,
        dimension=effective_dimension(rule, template),
        rule_level=template.level,
        severity=rule.severity,
        weight=rule.weight,
        catalog=catalog,
        schema=schema,
        table=table,
        column=column,
        status=status,
        threshold_metric=rule.threshold.metric,
        threshold_op=rule.threshold.op,
        threshold_value=rule.threshold.value,
        message=message[:MAX_MESSAGE_LENGTH] if message else None,
        **fields,
    )


def judge(rule: RuleInstance, measured: float | None) -> str:
    if measured is None:
        return STATUS_NO_DATA

    if rule.threshold.passes(measured):
        return STATUS_PASS

    return STATUS_FAIL if rule.severity == "error" else STATUS_WARN


def _number(value: Any) -> float | None:
    # Spark hands back Decimal for decimal-typed aggregates.
    return None if value is None else float(value)


def evaluate_counts(
    binding: Binding,
    location: dict[str, Any],
    passed: int,
    total: int,
    **fields: Any,
) -> ResultRecord:
    passed, total = int(passed or 0), int(total or 0)
    rate = passed / total if total else None
    status = judge(binding.rule, rate)

    if total == 0:
        fields.setdefault(
            "message",
            "No rows matched the row filter" if binding.rule.row_filter else "Table has no rows",
        )

    return record_for(
        binding.rule,
        binding.template,
        status,
        column=binding.column,
        total_count=total,
        pass_count=passed,
        fail_count=total - passed,
        metric_value=rate,
        **location,
        **fields,
    )


def evaluate_value(
    binding: Binding,
    location: dict[str, Any],
    value: Any,
    rows: int,
    **fields: Any,
) -> ResultRecord:
    measured = _number(value)
    status = judge(binding.rule, measured)

    if measured is None:
        fields.setdefault("message", "Table has no rows" if not rows else "No non-null values to measure")

    return record_for(
        binding.rule,
        binding.template,
        status,
        column=binding.column,
        total_count=int(rows or 0),
        metric_value=measured,
        **location,
        **fields,
    )


def error_record(binding: Binding, location: dict[str, Any], message: str, **fields: Any) -> ResultRecord:
    return record_for(
        binding.rule,
        binding.template,
        STATUS_ERROR,
        column=binding.column,
        message=message,
        **location,
        **fields,
    )


def skip_record(skip: Skip, location: dict[str, Any], **fields: Any) -> ResultRecord:
    return record_for(
        skip.rule,
        skip.template,
        STATUS_SKIPPED,
        column=skip.column,
        message=skip.reason,
        **location,
        **fields,
    )
