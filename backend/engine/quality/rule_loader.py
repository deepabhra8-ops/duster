from __future__ import annotations

import re
from typing import Any, Mapping

from engine.quality import families as F
from engine.quality.models import (
    DEFAULT_TABLE_TYPES,
    DIMENSIONS,
    NULL_POLICIES,
    SCOPE_LEVELS,
    SEVERITIES,
    TABLE_TYPES,
    THRESHOLD_OPS,
    RuleInstance,
    RuleValidationError,
    Scope,
    Threshold,
    finite_float,
)
from engine.quality.sql_text import check_sql_fragment
from engine.quality.templates import RuleTemplate, get_template


RULE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
MAX_DESCRIPTION_LENGTH = 1000
MAX_GLOB_LENGTH = 255
MAX_EXCLUDES = 50
MAX_EXCLUDE_LENGTH = 1024
MAX_WEIGHT = 1000.0


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise RuleValidationError(f"{field_name} must be an object")

    return value


def _choice(value: Any, choices: tuple[str, ...], field_name: str) -> str:
    text = str(value or "").strip()

    if text not in choices:
        raise RuleValidationError(f"{field_name} must be one of: {', '.join(choices)}")

    return text


def _glob(value: Any, field_name: str) -> str:
    if value is None:
        return "*"

    if not isinstance(value, str):
        raise RuleValidationError(f"scope.{field_name} must be a string")

    text = value.strip() or "*"

    if len(text) > MAX_GLOB_LENGTH:
        raise RuleValidationError(f"scope.{field_name} must be at most {MAX_GLOB_LENGTH} characters")

    if any(ord(char) < 32 for char in text):
        raise RuleValidationError(f"scope.{field_name} contains control characters")

    return text


def parse_scope(payload: Any) -> Scope:
    payload = _mapping(payload, "scope")

    raw_exclude = payload.get("exclude") or []

    if not isinstance(raw_exclude, (list, tuple)):
        raise RuleValidationError("scope.exclude must be a list of patterns")

    exclude: list[str] = []

    for pattern in raw_exclude:
        if not isinstance(pattern, str) or not pattern.strip():
            raise RuleValidationError("scope.exclude patterns must be non-empty strings")

        if len(pattern) > MAX_EXCLUDE_LENGTH:
            raise RuleValidationError(f"scope.exclude patterns must be at most {MAX_EXCLUDE_LENGTH} characters")

        if pattern.strip() not in exclude:
            exclude.append(pattern.strip())

    if len(exclude) > MAX_EXCLUDES:
        raise RuleValidationError(f"scope.exclude takes at most {MAX_EXCLUDES} patterns")

    raw_types = payload.get("tableTypes")
    table_types = DEFAULT_TABLE_TYPES if raw_types is None else raw_types

    if not isinstance(table_types, (list, tuple)):
        raise RuleValidationError("scope.tableTypes must be a list")

    table_types = tuple(dict.fromkeys(str(kind).strip().upper() for kind in table_types))

    if not table_types:
        raise RuleValidationError("scope.tableTypes needs at least one of: " + ", ".join(TABLE_TYPES))

    unknown = [kind for kind in table_types if kind not in TABLE_TYPES]

    if unknown:
        raise RuleValidationError(f"scope.tableTypes must be drawn from: {', '.join(TABLE_TYPES)}")

    level = payload.get("level")

    if level is not None:
        level = _choice(level, SCOPE_LEVELS, "scope.level")

    return Scope(
        catalog=_glob(payload.get("catalog"), "catalog"),
        schema=_glob(payload.get("schema"), "schema"),
        table=_glob(payload.get("table"), "table"),
        column=_glob(payload.get("column"), "column"),
        exclude=tuple(exclude),
        table_types=table_types,
        level=level,
    )


def parse_threshold(payload: Any, template: RuleTemplate) -> Threshold:
    if payload is None:
        return template.default_threshold

    payload = _mapping(payload, "threshold")
    metric = str(payload.get("metric") or template.threshold_metric).strip()

    if metric != template.threshold_metric:
        raise RuleValidationError(
            f"{template.name} is measured by {template.threshold_metric}, not {metric}"
        )

    op = _choice(payload.get("op", template.default_threshold.op), THRESHOLD_OPS, "threshold.op")
    value = finite_float(payload.get("value", template.default_threshold.value), "threshold.value")

    low, high = template.threshold_range

    if low is not None and value < low:
        raise RuleValidationError(f"threshold.value must be at least {low:g} for {template.name}")

    if high is not None and value > high:
        raise RuleValidationError(f"threshold.value must be at most {high:g} for {template.name}")

    return Threshold(metric=metric, op=op, value=value)


def parse_applies_to(value: Any, template: RuleTemplate) -> frozenset[str] | None:
    if value in (None, []):
        return None

    if not isinstance(value, (list, tuple)):
        raise RuleValidationError("appliesTo must be a list of type families")

    narrowed = frozenset(str(item).strip().lower() for item in value)
    unknown = sorted(narrowed - set(F.DECLARABLE))

    if unknown:
        raise RuleValidationError(f"Unknown type famil(ies): {', '.join(unknown)}")

    if F.ANY not in template.applies_to and not narrowed <= template.applies_to:
        raise RuleValidationError(
            f"{template.name} only applies to {F.describe(template.applies_to)}"
        )

    return narrowed


def parse_rule(
    payload: Mapping[str, Any],
    rule_id: str = "DRAFT",
    version: int = 1,
) -> RuleInstance:
    payload = _mapping(payload, "rule")

    name = str(payload.get("name") or "").strip()

    if not RULE_NAME_PATTERN.match(name):
        raise RuleValidationError(
            "name must start with a letter and use only letters, digits, '_', '-' or '.' (max 128)"
        )

    description = payload.get("description")

    if description is not None and len(str(description)) > MAX_DESCRIPTION_LENGTH:
        raise RuleValidationError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    template = get_template(payload.get("template"))
    params = template.normalize(_mapping(payload.get("params"), "params"))

    dimension = payload.get("dimension")

    if dimension not in (None, ""):
        dimension = _choice(str(dimension).lower(), DIMENSIONS, "dimension")
    else:
        dimension = None

    row_filter = payload.get("rowFilter")

    if row_filter is not None and not isinstance(row_filter, str):
        raise RuleValidationError("rowFilter must be a string")

    row_filter = check_sql_fragment(row_filter, "rowFilter") if row_filter and row_filter.strip() else None

    weight = finite_float(payload.get("weight", 1.0), "weight")

    if not 0 < weight <= MAX_WEIGHT:
        raise RuleValidationError(f"weight must be greater than 0 and at most {MAX_WEIGHT:g}")

    enabled = payload.get("enabled", True)

    if not isinstance(enabled, bool):
        raise RuleValidationError("enabled must be true or false")

    return RuleInstance(
        rule_id=rule_id,
        rule_name=name,
        template=template.name,
        params=params,
        scope=parse_scope(payload.get("scope")),
        threshold=parse_threshold(payload.get("threshold"), template),
        severity=_choice(payload.get("severity", "error"), SEVERITIES, "severity"),
        dimension=dimension,
        applies_to=parse_applies_to(payload.get("appliesTo"), template),
        null_policy=_choice(payload.get("nullPolicy", "ignore"), NULL_POLICIES, "nullPolicy"),
        row_filter=row_filter,
        weight=weight,
        version=version,
        enabled=enabled,
    )


def effective_families(rule: RuleInstance, template: RuleTemplate) -> frozenset[str]:
    return rule.applies_to or template.applies_to


def effective_dimension(rule: RuleInstance, template: RuleTemplate) -> str:
    return rule.dimension or template.dimension
