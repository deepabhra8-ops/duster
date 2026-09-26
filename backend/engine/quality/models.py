from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping


ENGINE_VERSION = "dq-1.0"

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_ERROR = "ERROR"
STATUS_NO_DATA = "NO_DATA"
STATUS_SKIPPED = "SKIPPED"

STATUSES = (STATUS_FAIL, STATUS_ERROR, STATUS_WARN, STATUS_NO_DATA, STATUS_PASS, STATUS_SKIPPED)

LEVEL_ROW = "row"
LEVEL_AGGREGATE = "aggregate"
LEVEL_TABLE = "table"
LEVEL_CROSS_TABLE = "cross_table"

# Levels whose pass/total counts are additive, so they can be summed across columns,
# tables, schemas and catalogs. Aggregate/table metrics (a uniqueness ratio, a max
# timestamp) are not, and only contribute to rollups through their status.
ADDITIVE_LEVELS = (LEVEL_ROW, LEVEL_CROSS_TABLE)

SEVERITIES = ("info", "warn", "error")
NULL_POLICIES = ("ignore", "fail")
THRESHOLD_METRICS = ("pass_rate", "value")
THRESHOLD_OPS = (">=", "<=", ">", "<", "==")
TABLE_TYPES = ("MANAGED", "EXTERNAL", "VIEW")
DEFAULT_TABLE_TYPES = ("MANAGED", "EXTERNAL")
SCOPE_LEVELS = ("column", "table", "schema", "catalog", "all")
DIMENSIONS = ("completeness", "validity", "uniqueness", "consistency", "accuracy", "timeliness")

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


class RuleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Scope:
    catalog: str = "*"
    schema: str = "*"
    table: str = "*"
    column: str = "*"
    exclude: tuple[str, ...] = ()
    table_types: tuple[str, ...] = DEFAULT_TABLE_TYPES
    level: str | None = None


@dataclass(frozen=True)
class Threshold:
    metric: str = "pass_rate"
    op: str = ">="
    value: float = 1.0

    def passes(self, measured: float) -> bool:
        return _OPS[self.op](measured, self.value)


@dataclass(frozen=True)
class RuleInstance:
    rule_id: str
    rule_name: str
    template: str
    threshold: Threshold
    params: Mapping[str, Any] = field(default_factory=dict)
    scope: Scope = Scope()
    severity: str = "error"
    dimension: str | None = None
    applies_to: frozenset[str] | None = None
    null_policy: str = "ignore"
    row_filter: str | None = None
    weight: float = 1.0
    version: int = 1
    enabled: bool = True


@dataclass(frozen=True)
class TableRef:
    catalog: str
    schema: str
    table: str
    kind: str = "TABLE"

    @property
    def fqn(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.table}"


@dataclass
class ResultRecord:
    rule_id: str
    rule_name: str
    rule_version: int
    template: str
    dimension: str
    rule_level: str
    severity: str
    weight: float
    catalog: str | None
    schema: str | None
    table: str | None
    column: str | None
    status: str
    threshold_metric: str
    threshold_op: str
    threshold_value: float
    total_count: int | None = None
    pass_count: int | None = None
    fail_count: int | None = None
    metric_value: float | None = None
    message: str | None = None
    where_clause: str | None = None
    sampled: bool = False
    sample_fraction: float | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise RuleValidationError(f"{field_name} must be a number")

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RuleValidationError(f"{field_name} must be a number") from None

    if not math.isfinite(number):
        raise RuleValidationError(f"{field_name} must be a finite number")

    return number
