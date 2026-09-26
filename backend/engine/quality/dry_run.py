from __future__ import annotations

from typing import Any

from engine.quality import families as F
from engine.quality.models import RuleInstance, TableRef
from engine.quality.planner import plan_bindings, plan_passes, prepare, render_scan_sql
from engine.quality.scope import ScopeResolver


DEFAULT_MAX_TABLES = 200
MAX_LISTED = 100


def dry_run(
    resolver: ScopeResolver,
    rules: list[RuleInstance],
    *,
    where: str | None = None,
    sample_fraction: float | None = None,
    max_exprs_per_pass: int = 400,
    max_tables: int = DEFAULT_MAX_TABLES,
) -> dict[str, Any]:
    """Resolve, validate and plan without scanning any data. Column types come from the
    source's metadata; the run itself re-checks them against each table's live schema."""
    plan: dict[TableRef, list[RuleInstance]] = {}
    excluded: set[TableRef] = set()
    errors: list[dict[str, Any]] = []

    for rule in rules:
        resolution = resolver.resolve(rule.scope)

        for table in resolution.tables:
            plan.setdefault(table, []).append(rule)

        excluded.update(resolution.excluded)

        for catalog, schema, message in resolution.errors:
            errors.append({"target": ".".join(p for p in (catalog, schema) if p), "message": message})

    tables = sorted(plan, key=lambda table: table.fqn.lower())
    inspected = tables[:max_tables]

    listed_tables: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    binding_errors: list[dict[str, Any]] = []
    binding_count = 0
    scan_tables = 0
    scan: dict[str, Any] | None = None

    for table in inspected:
        try:
            columns = resolver.columns(table.catalog, table.schema, table.table)
        except Exception as exc:
            errors.append({"target": table.fqn, "message": f"Couldn't read columns: {exc}"})
            continue

        bindings, skips = plan_bindings(table, columns, plan[table])
        prepared = [prepare(index, binding) for index, binding in enumerate(bindings)]
        binding_count += len(bindings)

        listed_tables.append({
            "catalog": table.catalog,
            "schema": table.schema,
            "table": table.table,
            "fqn": table.fqn,
            "kind": table.kind,
            "bindingCount": len(bindings),
            "columns": sorted({b.column for b in bindings if b.column}, key=str.lower),
            "typeUnverified": any(b.family == F.UNKNOWN for b in bindings),
        })

        skipped += [
            {"target": f"{table.fqn}.{skip.column}", "rule": skip.rule.rule_name, "reason": skip.reason}
            for skip in skips
        ]
        binding_errors += [
            {"target": f"{table.fqn}.{m.binding.column or ''}".rstrip("."), "rule": m.binding.rule.rule_name, "message": m.error}
            for m in prepared
            if m.error
        ]

        passes = plan_passes(prepared, max_exprs_per_pass, sampling=sample_fraction is not None)

        if passes:
            scan_tables += 1

            if scan is None:
                scan = {
                    "target": table.fqn,
                    "sql": render_scan_sql(table, passes[0], where, sample_fraction),
                    "passCount": len(passes),
                }

    return {
        "tableCount": len(tables),
        "inspectedTableCount": len(inspected),
        "truncated": len(tables) > len(inspected),
        "bindingCount": binding_count,
        "skippedCount": len(skipped),
        "excludedCount": len(excluded - set(plan)),
        "scanTableCount": scan_tables,
        "tables": listed_tables[:MAX_LISTED],
        "skipped": skipped[:MAX_LISTED],
        "bindingErrors": binding_errors[:MAX_LISTED],
        "errors": errors[:MAX_LISTED],
        "scan": scan,
    }
