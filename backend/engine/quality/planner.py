from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from engine.quality import families as F
from engine.quality.models import (
    LEVEL_AGGREGATE,
    LEVEL_CROSS_TABLE,
    LEVEL_ROW,
    LEVEL_TABLE,
    RuleInstance,
    TableRef,
)
from engine.quality.rule_loader import effective_families
from engine.quality.scope import glob_match, is_excluded, is_wildcard
from engine.quality.sql_text import display_fqn, number_literal, quote_ident
from engine.quality.templates import BindingError, BuildContext, RuleTemplate, get_template


ROWS_ALIAS = "__rows"
ROWS_EXPR = "count(1)"
DEFAULT_MAX_EXPRS_PER_PASS = 400
MAX_SEPARATE_EXPRS_PER_PASS = 8


@dataclass(frozen=True)
class Binding:
    rule: RuleInstance
    template: RuleTemplate
    column: str | None
    family: str | None


@dataclass(frozen=True)
class Skip:
    rule: RuleInstance
    template: RuleTemplate
    column: str
    reason: str


@dataclass(frozen=True)
class AggExpr:
    alias: str
    sql: str


@dataclass
class PreparedBinding:
    index: int
    binding: Binding
    exprs: list[AggExpr] = field(default_factory=list)
    predicate: str | None = None
    error: str | None = None

    @property
    def batchable(self) -> bool:
        return self.error is None and bool(self.exprs)


@dataclass
class ScanPass:
    exprs: list[AggExpr]
    members: list[PreparedBinding]
    sampled: bool = False


def plan_bindings(
    table: TableRef,
    columns: Sequence[tuple[str, str]],
    rules: Iterable[RuleInstance],
) -> tuple[list[Binding], list[Skip]]:
    """Expand rules × columns for one table against its column list. Type mismatches
    are reported as skips, never dropped, so coverage stays auditable."""
    bindings: list[Binding] = []
    skips: list[Skip] = []

    for rule in rules:
        template = get_template(rule.template)

        if not template.needs_column:
            bindings.append(Binding(rule, template, None, None))
            continue

        pattern = rule.scope.column
        allowed = effective_families(rule, template)
        matched = False

        for name, family in columns:
            if not glob_match(pattern, name):
                continue

            if is_excluded(rule.scope.exclude, table.catalog, table.schema, table.table, name):
                continue

            matched = True

            if F.fits(allowed, family):
                bindings.append(Binding(rule, template, name, family))
            else:
                skips.append(Skip(rule, template, name, f"type {family} not in {F.describe(allowed)}"))

        if not matched and not is_wildcard(pattern):
            skips.append(Skip(rule, template, pattern, "column not found in table"))

    return bindings, skips


def filter_sql(rule: RuleInstance) -> str | None:
    return f"coalesce(({rule.row_filter}), false)" if rule.row_filter else None


def predicate_sql(binding: Binding) -> str:
    rule, template = binding.rule, binding.template
    column = quote_ident(binding.column) if binding.column else None
    check = template.build(BuildContext(params=rule.params, family=binding.family, column=column, value=column))

    if template.null_policy_applies and column:
        if rule.null_policy == "fail":
            return f"{column} IS NOT NULL AND ({check})"

        return f"{column} IS NULL OR ({check})"

    return check


def prepare(index: int, binding: Binding) -> PreparedBinding:
    rule, template = binding.rule, binding.template
    prepared = PreparedBinding(index=index, binding=binding)

    if template.level == LEVEL_CROSS_TABLE:
        return prepared

    row_filter = filter_sql(rule)

    try:
        if template.level == LEVEL_ROW:
            prepared.predicate = predicate_sql(binding)
            passed = f"coalesce(({prepared.predicate}), false)"

            if row_filter:
                prepared.exprs = [
                    AggExpr(f"p{index}", f"count_if({row_filter} AND {passed})"),
                    AggExpr(f"t{index}", f"count_if({row_filter})"),
                ]
            else:
                prepared.exprs = [AggExpr(f"p{index}", f"count_if({passed})")]

        elif template.level in (LEVEL_AGGREGATE, LEVEL_TABLE):
            column = quote_ident(binding.column) if binding.column else None
            value = f"CASE WHEN {row_filter} THEN {column} END" if row_filter and column else column
            rows = f"CASE WHEN {row_filter} THEN 1 END" if row_filter else "1"
            context = BuildContext(params=rule.params, family=binding.family, column=column, value=value, rows=rows)
            prepared.exprs = [AggExpr(f"v{index}", template.build(context))]

    except BindingError as exc:
        prepared.error = str(exc)

    return prepared


def _chunk(members: list[PreparedBinding], limit: int, sampled: bool) -> list[ScanPass]:
    passes: list[ScanPass] = []
    current: list[PreparedBinding] = []
    size = 0

    for member in members:
        if current and size + len(member.exprs) > limit:
            passes.append(_make_pass(current, sampled))
            current, size = [], 0

        current.append(member)
        size += len(member.exprs)

    if current:
        passes.append(_make_pass(current, sampled))

    return passes


def _make_pass(members: list[PreparedBinding], sampled: bool) -> ScanPass:
    exprs = [AggExpr(ROWS_ALIAS, ROWS_EXPR)]

    for member in members:
        exprs.extend(member.exprs)

    return ScanPass(exprs=exprs, members=members, sampled=sampled)


def plan_passes(
    prepared: Iterable[PreparedBinding],
    max_exprs_per_pass: int = DEFAULT_MAX_EXPRS_PER_PASS,
    sampling: bool = False,
) -> list[ScanPass]:
    """Group a table's batchable bindings into as few single-row aggregate scans as
    possible. Sampling splits sample-safe checks from those that need every row
    (existence, uniqueness, freshness), and exact distinct counts get their own passes."""
    groups: dict[tuple[bool, bool], list[PreparedBinding]] = {}

    for member in prepared:
        if not member.batchable:
            continue

        template = member.binding.template
        sampled = sampling and template.sample_safe
        separate = template.separate_pass(member.binding.rule.params)
        groups.setdefault((separate, sampled), []).append(member)

    limit = max(2, max_exprs_per_pass - 1)
    passes: list[ScanPass] = []

    for (separate, sampled), members in sorted(groups.items()):
        passes.extend(_chunk(members, MAX_SEPARATE_EXPRS_PER_PASS if separate else limit, sampled))

    return passes


def render_scan_sql(
    table: TableRef,
    scan_pass: ScanPass,
    where: str | None = None,
    sample_fraction: float | None = None,
) -> str:
    lines = ["SELECT " + f"{scan_pass.exprs[0].sql} AS {scan_pass.exprs[0].alias},"]
    lines += [f"  {expr.sql} AS {expr.alias}," for expr in scan_pass.exprs[1:]]
    lines[-1] = lines[-1].rstrip(",")

    source = f"FROM {display_fqn(table.catalog, table.schema, table.table)}"

    if scan_pass.sampled and sample_fraction:
        source += f" TABLESAMPLE ({number_literal(round(sample_fraction * 100, 4))} PERCENT)"

    lines.append(source)

    if where:
        lines.append(f"WHERE {where}")

    return "\n".join(lines)
