from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Mapping

from engine.quality import families as F
from engine.quality.models import (
    LEVEL_AGGREGATE,
    LEVEL_CROSS_TABLE,
    LEVEL_ROW,
    LEVEL_TABLE,
    RuleValidationError,
    Threshold,
    finite_float,
)
from engine.quality.sql_text import (
    check_sql_fragment,
    number_literal,
    parse_number,
    parse_temporal,
    string_literal,
    temporal_literal,
)


class BindingError(Exception):
    """The rule's parameters don't fit this particular column (e.g. date bounds on a
    numeric column). Recorded as an ERROR result for that binding only."""


@dataclass(frozen=True)
class BuildContext:
    params: Mapping[str, Any]
    family: str | None = None
    # `column` is the quoted identifier. `value` is the same column, but wrapped in
    # CASE WHEN <row filter> THEN column END when the rule has a row filter, so
    # aggregate templates (count, count distinct, max) only see matching rows.
    column: str | None = None
    value: str | None = None
    # Argument for count(...) that counts only rows matching the rule's filter.
    rows: str = "1"


@dataclass(frozen=True)
class RuleTemplate:
    name: str
    level: str
    dimension: str
    applies_to: frozenset[str]
    default_threshold: Threshold
    normalize: Callable[[Mapping[str, Any]], dict[str, Any]]
    build: Callable[[BuildContext], str] | None
    description: str = ""
    threshold_unit: str = "pass_rate"
    threshold_range: tuple[float | None, float | None] = (0.0, 1.0)
    needs_column: bool = True
    sample_safe: bool = True
    null_policy_applies: bool = False
    separate_pass: Callable[[Mapping[str, Any]], bool] = field(default=lambda params: False)

    @property
    def threshold_metric(self) -> str:
        return "pass_rate" if self.level in (LEVEL_ROW, LEVEL_CROSS_TABLE) else "value"


REGISTRY: dict[str, RuleTemplate] = {}


def register(template: RuleTemplate) -> RuleTemplate:
    if template.name in REGISTRY:
        raise ValueError(f"Rule template '{template.name}' is already registered")

    REGISTRY[template.name] = template
    return template


def get_template(name: str) -> RuleTemplate:
    template = REGISTRY.get(str(name or "").strip())

    if template is None:
        raise RuleValidationError(f"Unknown template '{name}'")

    return template


# ---- parameter helpers ----

def _only(params: Mapping[str, Any], allowed: tuple[str, ...], template: str) -> None:
    unknown = sorted(set(params) - set(allowed))

    if unknown:
        raise RuleValidationError(f"{template} does not take parameter(s): {', '.join(unknown)}")


def _flag(params: Mapping[str, Any], key: str, default: bool) -> bool:
    value = params.get(key, default)

    if not isinstance(value, bool):
        raise RuleValidationError(f"{key} must be true or false")

    return value


def _text(params: Mapping[str, Any], key: str, template: str, max_length: int = 1000) -> str:
    value = params.get(key)

    if not isinstance(value, str) or not value.strip():
        raise RuleValidationError(f"{template} needs a {key}")

    if len(value) > max_length:
        raise RuleValidationError(f"{key} must be at most {max_length} characters")

    return value.strip()


def _no_params(name: str) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def normalize(params: Mapping[str, Any]) -> dict[str, Any]:
        _only(params, (), name)
        return {}

    return normalize


def _bound(value: Any, key: str) -> int | float | str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    number = parse_number(value)

    if number is not None:
        return number

    temporal = parse_temporal(value)

    if temporal is not None:
        return temporal.isoformat()

    raise RuleValidationError(f"{key} must be a number or an ISO date/timestamp")


def _is_temporal_bound(value: Any) -> bool:
    return isinstance(value, str)


def _as_datetime(value: date | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)


def _range_literal(value: int | float | str, family: str | None, key: str) -> str:
    if family == F.UNKNOWN:
        family = F.TEMPORAL if _is_temporal_bound(value) else F.NUMERIC

    if family == F.TEMPORAL:
        if not _is_temporal_bound(value):
            raise BindingError(f"{key} {value} is a number, but the column is temporal")

        return temporal_literal(parse_temporal(value))

    if _is_temporal_bound(value):
        raise BindingError(f"{key} {value} is a date, but the column is {family}")

    return number_literal(value)


def _values(raw: Any) -> list[str]:
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = raw
    else:
        raise RuleValidationError("values must be a list or a comma-separated string")

    cleaned: list[str] = []

    for item in items:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise RuleValidationError("values must be strings or numbers")

        text = str(item).strip()

        if text and text not in cleaned:
            cleaned.append(text)

    return cleaned


# ---- templates ----

def _normalize_in_range(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("min", "max", "boundsInclusive"), "in_range")
    low = _bound(params.get("min"), "min")
    high = _bound(params.get("max"), "max")

    if low is None and high is None:
        raise RuleValidationError("in_range needs a min, a max, or both")

    if low is not None and high is not None:
        _check_bounds_ordered(low, high)

    return {"min": low, "max": high, "boundsInclusive": _flag(params, "boundsInclusive", True)}


def _check_bounds_ordered(low: int | float | str, high: int | float | str) -> None:
    if _is_temporal_bound(low) != _is_temporal_bound(high):
        raise RuleValidationError("min and max must both be numbers or both be dates")

    if _is_temporal_bound(low):
        ordered = _as_datetime(parse_temporal(low)) <= _as_datetime(parse_temporal(high))
    else:
        ordered = low <= high

    if not ordered:
        raise RuleValidationError("min must not be greater than max")


def _build_in_range(ctx: BuildContext) -> str:
    inclusive = ctx.params.get("boundsInclusive", True)
    checks = []

    if ctx.params.get("min") is not None:
        checks.append(f"{ctx.column} {'>=' if inclusive else '>'} {_range_literal(ctx.params['min'], ctx.family, 'min')}")

    if ctx.params.get("max") is not None:
        checks.append(f"{ctx.column} {'<=' if inclusive else '<'} {_range_literal(ctx.params['max'], ctx.family, 'max')}")

    return " AND ".join(checks)


def _normalize_allowed_values(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("values", "matchCase"), "allowed_values")
    values = _values(params.get("values", []))

    if not values:
        raise RuleValidationError("allowed_values needs at least one value")

    if len(values) > 5000:
        raise RuleValidationError("allowed_values takes at most 5000 values")

    return {"values": values, "matchCase": _flag(params, "matchCase", True)}


def _build_allowed_values(ctx: BuildContext) -> str:
    values = ctx.params["values"]

    if ctx.family == F.NUMERIC or (ctx.family == F.UNKNOWN and all(parse_number(v) is not None for v in values)):
        numbers = [parse_number(value) for value in values]
        bad = [value for value, number in zip(values, numbers) if number is None]

        if bad:
            raise BindingError(f"'{bad[0]}' is not a number, but the column is numeric")

        return f"{ctx.column} IN ({', '.join(number_literal(n) for n in numbers)})"

    if ctx.params.get("matchCase", True):
        return f"{ctx.column} IN ({', '.join(string_literal(v) for v in values)})"

    lowered = dict.fromkeys(value.lower() for value in values)
    return f"lower({ctx.column}) IN ({', '.join(string_literal(v) for v in lowered)})"


def _normalize_regex(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("pattern", "fullValue"), "regex_match")
    return {
        "pattern": _text(params, "pattern", "regex_match"),
        "fullValue": _flag(params, "fullValue", True),
    }


def full_value_pattern(params: Mapping[str, Any]) -> str:
    pattern = params["pattern"]
    # Spark's RLIKE finds the pattern anywhere in the value; anchoring the whole
    # pattern gives "the full value must match" semantics.
    return f"^(?:{pattern})$" if params.get("fullValue", True) else pattern


def _build_regex(ctx: BuildContext) -> str:
    return f"{ctx.column} RLIKE {string_literal(full_value_pattern(ctx.params))}"


def _normalize_unique_ratio(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("exact", "maxRsd"), "unique_ratio")
    max_rsd = finite_float(params.get("maxRsd", 0.05), "maxRsd")

    if not 0.001 <= max_rsd <= 0.3:
        raise RuleValidationError("maxRsd must be between 0.001 and 0.3")

    return {"exact": _flag(params, "exact", False), "maxRsd": max_rsd}


def _build_unique_ratio(ctx: BuildContext) -> str:
    if ctx.params.get("exact"):
        distinct = f"count(DISTINCT {ctx.value})"
    else:
        distinct = f"approx_count_distinct({ctx.value}, {number_literal(ctx.params.get('maxRsd', 0.05))}D)"

    # The approximate count can overshoot the exact one slightly, so the ratio is capped
    # at 1. An all-null column has no ratio (NO_DATA), not a ratio of 0.
    return (
        f"CASE WHEN count({ctx.value}) = 0 THEN NULL "
        f"ELSE least(1D, {distinct} / count({ctx.value})) END"
    )


FRESHNESS_REFERENCES = ("current_timestamp()",)


def _normalize_freshness(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("measuredAgainst",), "freshness_hours")
    reference = params.get("measuredAgainst", FRESHNESS_REFERENCES[0])

    if reference not in FRESHNESS_REFERENCES:
        raise RuleValidationError(f"measuredAgainst must be one of: {', '.join(FRESHNESS_REFERENCES)}")

    return {"measuredAgainst": reference}


def _build_freshness(ctx: BuildContext) -> str:
    return (
        f"(unix_timestamp({ctx.params.get('measuredAgainst', FRESHNESS_REFERENCES[0])}) "
        f"- unix_timestamp(max({ctx.value}))) / 3600D"
    )


def parse_parent_table(value: str) -> tuple[str | None, str, str]:
    """Split "[catalog.]schema.table" from the right, so a connection name containing
    dots still works as the catalog. A missing catalog means "same as the child"."""
    parts = value.split(".")

    if len(parts) < 2 or any(not part.strip() for part in parts):
        raise RuleValidationError("parentTable must look like schema.table or catalog.schema.table")

    if any(char in value for char in "*?["):
        raise RuleValidationError("parentTable must name one table, not a pattern")

    catalog = ".".join(parts[:-2]).strip() or None
    return catalog, parts[-2].strip(), parts[-1].strip()


def _normalize_referential(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("parentTable", "parentColumn"), "referential_integrity")
    parent_table = _text(params, "parentTable", "referential_integrity", max_length=800)
    parse_parent_table(parent_table)
    return {
        "parentTable": parent_table,
        "parentColumn": _text(params, "parentColumn", "referential_integrity", max_length=255),
    }


def _normalize_sql_row(params: Mapping[str, Any]) -> dict[str, Any]:
    _only(params, ("expression",), "sql_row")
    expression = params.get("expression")

    if not isinstance(expression, str):
        raise RuleValidationError("sql_row needs an expression")

    return {"expression": check_sql_fragment(expression, "expression")}


def _build_sql_row(ctx: BuildContext) -> str:
    return f"({ctx.params['expression'].replace('{column}', ctx.column or '')})"


_PASS_RATE_99 = Threshold("pass_rate", ">=", 0.99)
_PASS_RATE_ALL = Threshold("pass_rate", ">=", 1.0)

register(RuleTemplate(
    name="not_null",
    level=LEVEL_ROW,
    dimension="completeness",
    applies_to=frozenset({F.ANY}),
    default_threshold=_PASS_RATE_ALL,
    normalize=_no_params("not_null"),
    build=lambda ctx: f"{ctx.column} IS NOT NULL",
    description="Value is present. A null always fails, so the null policy doesn't apply.",
    sample_safe=False,
))

register(RuleTemplate(
    name="not_blank",
    level=LEVEL_ROW,
    dimension="completeness",
    applies_to=frozenset({F.STRING}),
    default_threshold=_PASS_RATE_99,
    normalize=_no_params("not_blank"),
    # \S rather than trim(): Spark's trim only strips spaces, not tabs or newlines.
    build=lambda ctx: f"{ctx.column} IS NOT NULL AND {ctx.column} RLIKE {string_literal(chr(92) + 'S')}",
    description="Value is non-null and contains something other than whitespace.",
))

register(RuleTemplate(
    name="in_range",
    level=LEVEL_ROW,
    dimension="validity",
    applies_to=frozenset({F.NUMERIC, F.TEMPORAL}),
    default_threshold=_PASS_RATE_99,
    normalize=_normalize_in_range,
    build=_build_in_range,
    description="Value lies between min and max.",
    null_policy_applies=True,
))

register(RuleTemplate(
    name="allowed_values",
    level=LEVEL_ROW,
    dimension="validity",
    applies_to=frozenset({F.STRING, F.NUMERIC}),
    default_threshold=_PASS_RATE_99,
    normalize=_normalize_allowed_values,
    build=_build_allowed_values,
    description="Value is one of a fixed list.",
    null_policy_applies=True,
))

register(RuleTemplate(
    name="regex_match",
    level=LEVEL_ROW,
    dimension="validity",
    applies_to=frozenset({F.STRING}),
    default_threshold=_PASS_RATE_99,
    normalize=_normalize_regex,
    build=_build_regex,
    description="Value matches a (Java) regular expression.",
    null_policy_applies=True,
))

register(RuleTemplate(
    name="unique_ratio",
    level=LEVEL_AGGREGATE,
    dimension="uniqueness",
    applies_to=frozenset({F.NUMERIC, F.STRING, F.TEMPORAL}),
    default_threshold=Threshold("value", ">=", 0.995),
    normalize=_normalize_unique_ratio,
    build=_build_unique_ratio,
    description="Distinct values divided by non-null values.",
    threshold_unit="ratio",
    sample_safe=False,
    # Exact distinct counts make Spark expand every row once per distinct aggregate,
    # which would slow down every other check sharing the scan, so they get their own.
    separate_pass=lambda params: bool(params.get("exact")),
))

register(RuleTemplate(
    name="freshness_hours",
    level=LEVEL_AGGREGATE,
    dimension="timeliness",
    applies_to=frozenset({F.TEMPORAL}),
    default_threshold=Threshold("value", "<=", 24.0),
    normalize=_normalize_freshness,
    build=_build_freshness,
    description="Hours between now and the newest value.",
    threshold_unit="hours",
    threshold_range=(0.0, None),
    sample_safe=False,
))

register(RuleTemplate(
    name="row_count",
    level=LEVEL_TABLE,
    dimension="completeness",
    applies_to=frozenset(),
    default_threshold=Threshold("value", ">=", 1.0),
    normalize=_no_params("row_count"),
    build=lambda ctx: f"count({ctx.rows})",
    description="Number of rows in the table. Binds once per table.",
    threshold_unit="rows",
    threshold_range=(0.0, None),
    needs_column=False,
    sample_safe=False,
))

register(RuleTemplate(
    name="referential_integrity",
    level=LEVEL_CROSS_TABLE,
    dimension="consistency",
    applies_to=frozenset({F.NUMERIC, F.STRING}),
    default_threshold=_PASS_RATE_ALL,
    normalize=_normalize_referential,
    build=None,
    description="Every non-null key exists in the parent table. Runs as its own join.",
    sample_safe=False,
))

register(RuleTemplate(
    name="sql_row",
    level=LEVEL_ROW,
    dimension="validity",
    applies_to=frozenset({F.ANY}),
    default_threshold=_PASS_RATE_99,
    normalize=_normalize_sql_row,
    build=_build_sql_row,
    description="Custom boolean Spark SQL expression; {column} becomes the quoted column.",
))


def describe_templates() -> list[dict[str, Any]]:
    return [
        {
            "name": template.name,
            "level": template.level,
            "dimension": template.dimension,
            "appliesTo": sorted(template.applies_to),
            "needsColumn": template.needs_column,
            "sampleSafe": template.sample_safe,
            "nullPolicyApplies": template.null_policy_applies,
            "thresholdMetric": template.threshold_metric,
            "thresholdUnit": template.threshold_unit,
            "defaultThreshold": {
                "metric": template.default_threshold.metric,
                "op": template.default_threshold.op,
                "value": template.default_threshold.value,
            },
            "description": template.description,
        }
        for template in REGISTRY.values()
    ]
