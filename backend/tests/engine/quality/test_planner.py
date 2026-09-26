from __future__ import annotations

from engine.quality.models import TableRef
from engine.quality.planner import plan_bindings, plan_passes, prepare, render_scan_sql
from engine.quality.rule_loader import parse_rule


ORDERS = TableRef("main", "sales", "orders")
COLUMNS = [
    ("order_id", "numeric"),
    ("order_amount", "numeric"),
    ("tax_amount", "numeric"),
    ("raw_amount", "string"),
    ("updated_at", "temporal"),
    ("status", "string"),
]


def rule(name, template, column="*", **extra):
    payload = {"name": name, "template": template, "scope": {"column": column, **extra.pop("scope", {})}, **extra}
    return parse_rule(payload, rule_id=f"R_{name}")


def test_column_glob_binds_matching_columns_and_skips_type_mismatches():
    in_range = rule("amounts", "in_range", "*_amount", params={"min": 0, "max": 100})
    bindings, skips = plan_bindings(ORDERS, COLUMNS, [in_range])

    assert [b.column for b in bindings] == ["order_amount", "tax_amount"]
    assert [(s.column, s.reason) for s in skips] == [("raw_amount", "type string not in [numeric, temporal]")]


def test_table_level_templates_bind_once_without_a_column():
    bindings, skips = plan_bindings(ORDERS, COLUMNS, [rule("rows", "row_count", "*_amount")])

    assert [(b.column, b.template.name) for b in bindings] == [(None, "row_count")]
    assert skips == []


def test_exact_column_that_does_not_exist_is_reported():
    bindings, skips = plan_bindings(ORDERS, COLUMNS, [rule("pk", "not_null", "customer_id")])

    assert bindings == []
    assert [(s.column, s.reason) for s in skips] == [("customer_id", "column not found in table")]


def test_wildcard_that_matches_nothing_is_silent():
    bindings, skips = plan_bindings(ORDERS, COLUMNS, [rule("pk", "not_null", "*_code")])
    assert bindings == [] and skips == []


def test_four_part_excludes_drop_columns():
    excluded = rule("pk", "not_null", "*", scope={"exclude": ["main.sales.orders.raw_*"]})
    bindings, _ = plan_bindings(ORDERS, COLUMNS, [excluded])

    assert "raw_amount" not in [b.column for b in bindings]
    assert len(bindings) == len(COLUMNS) - 1


def test_applies_to_narrowing():
    narrowed = rule("present", "not_null", "*", appliesTo=["temporal"])
    bindings, skips = plan_bindings(ORDERS, COLUMNS, [narrowed])

    assert [b.column for b in bindings] == ["updated_at"]
    assert len(skips) == len(COLUMNS) - 1


def test_unknown_family_binds_provisionally():
    bindings, skips = plan_bindings(ORDERS, [("Amount__c", "unknown")], [rule("a", "in_range", "*", params={"min": 0})])
    assert [b.column for b in bindings] == ["Amount__c"] and skips == []


def test_row_binding_counts_with_null_policy():
    ignore = prepare(0, plan_bindings(ORDERS, COLUMNS, [rule("r", "in_range", "order_amount", params={"min": 0})])[0][0])
    fail = prepare(1, plan_bindings(ORDERS, COLUMNS, [rule("r", "in_range", "order_amount", params={"min": 0}, nullPolicy="fail")])[0][0])

    assert [(e.alias, e.sql) for e in ignore.exprs] == [
        ("p0", "count_if(coalesce((`order_amount` IS NULL OR (`order_amount` >= 0)), false))"),
    ]
    assert fail.exprs[0].sql == "count_if(coalesce((`order_amount` IS NOT NULL AND (`order_amount` >= 0)), false))"


def test_row_filter_adds_a_filtered_total():
    filtered = rule("r", "not_null", "order_id", rowFilter="status <> 'cancelled'")
    prepared = prepare(3, plan_bindings(ORDERS, COLUMNS, [filtered])[0][0])

    assert [(e.alias, e.sql) for e in prepared.exprs] == [
        ("p3", "count_if(coalesce((status <> 'cancelled'), false) AND coalesce((`order_id` IS NOT NULL), false))"),
        ("t3", "count_if(coalesce((status <> 'cancelled'), false))"),
    ]


def test_row_filter_wraps_aggregate_values():
    filtered = rule("fresh", "freshness_hours", "updated_at", rowFilter="status = 'open'")
    prepared = prepare(0, plan_bindings(ORDERS, COLUMNS, [filtered])[0][0])

    assert "max(CASE WHEN coalesce((status = 'open'), false) THEN `updated_at` END)" in prepared.exprs[0].sql


def test_binding_errors_are_captured_per_binding():
    temporal_bounds = rule("r", "in_range", "order_amount", params={"min": "2024-01-01"})
    prepared = prepare(0, plan_bindings(ORDERS, COLUMNS, [temporal_bounds])[0][0])

    assert prepared.error and "is a date" in prepared.error
    assert not prepared.batchable


def test_cross_table_bindings_are_not_batched():
    fk = rule("fk", "referential_integrity", "order_id", params={"parentTable": "main.sales.customers", "parentColumn": "id"})
    prepared = prepare(0, plan_bindings(ORDERS, COLUMNS, [fk])[0][0])

    assert prepared.exprs == [] and prepared.error is None
    assert plan_passes([prepared]) == []


def _prepared(rules):
    bindings, _ = plan_bindings(ORDERS, COLUMNS, rules)
    return [prepare(index, binding) for index, binding in enumerate(bindings)]


def test_everything_shares_one_pass_with_a_single_row_count():
    prepared = _prepared([rule("nn", "not_null"), rule("rows", "row_count"), rule("u", "unique_ratio", "order_id")])
    passes = plan_passes(prepared)

    assert len(passes) == 1
    assert passes[0].exprs[0].alias == "__rows"
    assert [e.alias for e in passes[0].exprs].count("__rows") == 1
    assert len(passes[0].members) == len(COLUMNS) + 2


def test_wide_tables_are_chunked_without_splitting_a_binding():
    prepared = _prepared([rule("nn", "not_null", rowFilter="status IS NOT NULL")])
    passes = plan_passes(prepared, max_exprs_per_pass=5)

    assert all(len(p.exprs) <= 5 for p in passes)
    assert sum(len(p.members) for p in passes) == len(COLUMNS)

    for scan_pass in passes:
        aliases = {e.alias for e in scan_pass.exprs}
        for member in scan_pass.members:
            assert {e.alias for e in member.exprs} <= aliases


def test_exact_distinct_counts_get_their_own_pass():
    prepared = _prepared([rule("nn", "not_null", "order_id"), rule("u", "unique_ratio", "order_id", params={"exact": True})])
    passes = plan_passes(prepared)

    assert len(passes) == 2
    assert [[m.binding.template.name for m in p.members] for p in passes] == [["not_null"], ["unique_ratio"]]


def test_sampling_splits_sample_safe_checks_from_full_scan_ones():
    prepared = _prepared([rule("range", "in_range", "order_amount", params={"min": 0}), rule("nn", "not_null", "order_id")])
    passes = plan_passes(prepared, sampling=True)

    by_sampled = {p.sampled: [m.binding.template.name for m in p.members] for p in passes}
    assert by_sampled == {False: ["not_null"], True: ["in_range"]}


def test_render_scan_sql():
    prepared = _prepared([rule("range", "in_range", "order_amount", params={"min": 0, "max": 250000})])
    scan_pass = plan_passes(prepared, sampling=True)[0]

    assert render_scan_sql(ORDERS, scan_pass, where="event_date = current_date()", sample_fraction=0.1) == (
        "SELECT count(1) AS __rows,\n"
        "  count_if(coalesce((`order_amount` IS NULL OR (`order_amount` >= 0 AND `order_amount` <= 250000)), false)) AS p0\n"
        "FROM main.sales.orders TABLESAMPLE (10 PERCENT)\n"
        "WHERE event_date = current_date()"
    )
