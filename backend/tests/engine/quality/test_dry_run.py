from __future__ import annotations

from engine.quality.dry_run import dry_run
from engine.quality.rule_loader import parse_rule
from engine.quality.scope import ScopeResolver

from tests.engine.quality.fakes import FakeCatalog


TREE = {
    "main": {
        "sales": {
            "orders": [("order_amount", "numeric"), ("tax_amount", "numeric"), ("raw_amount", "string")],
            "refunds": [("refund_amount", "numeric")],
            "notes": [("body", "string")],
        },
        "sales_tmp": {"scratch": [("x_amount", "numeric")]},
    },
}


def amounts_rule(**scope):
    return parse_rule({
        "name": "amounts_in_range",
        "template": "in_range",
        "params": {"min": 0, "max": 250000},
        "scope": {"catalog": "main", "schema": "sales*", "column": "*_amount", "exclude": ["main.sales_tmp.*"], **scope},
    })


def test_dry_run_plans_without_scanning():
    plan = dry_run(ScopeResolver(FakeCatalog(TREE)), [amounts_rule()])

    assert plan["tableCount"] == 3
    assert plan["bindingCount"] == 3
    assert plan["skippedCount"] == 1
    assert plan["excludedCount"] == 1
    assert plan["truncated"] is False
    assert [(t["fqn"], t["bindingCount"], t["columns"]) for t in plan["tables"]] == [
        ("main.sales.notes", 0, []),
        ("main.sales.orders", 2, ["order_amount", "tax_amount"]),
        ("main.sales.refunds", 1, ["refund_amount"]),
    ]
    assert plan["skipped"] == [
        {"target": "main.sales.orders.raw_amount", "rule": "amounts_in_range", "reason": "type string not in [numeric, temporal]"},
    ]
    assert plan["scan"]["target"] == "main.sales.orders"
    assert plan["scan"]["sql"].startswith("SELECT count(1) AS __rows,")
    assert plan["scanTableCount"] == 2


def test_dry_run_caps_inspected_tables():
    plan = dry_run(ScopeResolver(FakeCatalog(TREE)), [amounts_rule()], max_tables=1)

    assert plan["tableCount"] == 3
    assert plan["inspectedTableCount"] == 1
    assert plan["truncated"] is True


def test_dry_run_reports_metadata_errors_and_binding_errors():
    catalog = FakeCatalog(TREE, failing={("main", "sales", "refunds"): "timeout"})
    rule = parse_rule({
        "name": "dates",
        "template": "in_range",
        "params": {"min": "2020-01-01"},
        "scope": {"catalog": "main", "schema": "sales", "table": "orders", "column": "order_amount"},
    })

    plan = dry_run(ScopeResolver(catalog), [rule, amounts_rule(table="refunds")])

    assert {"target": "main.sales.refunds", "message": "Couldn't read columns: timeout"} in plan["errors"]
    assert plan["bindingErrors"][0]["target"] == "main.sales.orders.order_amount"
    assert "is a date" in plan["bindingErrors"][0]["message"]
