from __future__ import annotations

import pytest

from engine.quality.models import Scope, TableRef
from engine.quality.scope import ScopeResolver, glob_match, is_excluded, kind_allowed

from tests.engine.quality.fakes import FakeCatalog


TREE = {
    "main": {
        "sales": {"orders": [], "order_lines": [], "_bak_orders": [], "v_orders": []},
        "sales_eu": {"orders_eu": []},
        "sales_tmp": {"scratch": []},
        "information_schema": {"tables": []},
        "marketing": {"leads": []},
    },
    "ops": {"web": {"page_views": []}},
}


@pytest.mark.parametrize(
    ("pattern", "value", "expected"),
    [
        ("*", "anything", True),
        (None, "anything", True),
        ("sales*", "sales_eu", True),
        ("sales*", "marketing", False),
        ("SALES", "sales", True),
        ("*_amount", "order_amount", True),
        ("?ales", "sales", True),
    ],
)
def test_glob_match_is_case_insensitive(pattern, value, expected):
    assert glob_match(pattern, value) is expected


def test_is_excluded_three_and_four_part_patterns():
    assert is_excluded(["main.sales_tmp.*"], "main", "sales_tmp", "scratch")
    assert is_excluded(["*.*._bak_*"], "main", "sales", "_bak_orders")
    assert not is_excluded(["*.*._bak_*"], "main", "sales", "orders")

    # A 4-part pattern only ever excludes columns, never the whole table.
    assert not is_excluded(["main.sales.orders.raw_*"], "main", "sales", "orders")
    assert is_excluded(["main.sales.orders.raw_*"], "main", "sales", "orders", "raw_amount")

    # Anything else matches the dotted name as a whole, where * spans dots.
    assert is_excluded(["ops.*"], "ops", "web", "page_views")


def test_kind_allowed_maps_uc_table_types_onto_tables_and_views():
    assert kind_allowed("TABLE", ["MANAGED"])
    assert kind_allowed("TABLE", ["EXTERNAL"])
    assert not kind_allowed("TABLE", ["VIEW"])
    assert kind_allowed("VIEW", ["VIEW"])
    assert not kind_allowed("VIEW", ["MANAGED", "EXTERNAL"])


def fqns(tables):
    return [table.fqn for table in tables]


def test_resolve_schema_glob_with_excludes_and_table_types():
    resolver = ScopeResolver(FakeCatalog(TREE))
    resolution = resolver.resolve(Scope("main", "sales*", "*", exclude=("main.sales_tmp.*", "*.*._bak_*")))

    assert fqns(resolution.tables) == ["main.sales.order_lines", "main.sales.orders", "main.sales_eu.orders_eu"]
    assert sorted(fqns(resolution.excluded)) == ["main.sales._bak_orders", "main.sales_tmp.scratch"]


def test_views_only_when_asked_for():
    resolver = ScopeResolver(FakeCatalog(TREE))
    resolution = resolver.resolve(Scope("main", "sales", "*", table_types=("VIEW",)))

    assert fqns(resolution.tables) == ["main.sales.v_orders"]


def test_system_schemas_are_skipped_by_wildcards_but_reachable_by_name():
    resolver = ScopeResolver(FakeCatalog(TREE))

    assert "main.information_schema.tables" not in fqns(resolver.resolve(Scope("main")).tables)
    assert fqns(resolver.resolve(Scope("main", "information_schema")).tables) == ["main.information_schema.tables"]


def test_everything_scope_spans_catalogs():
    resolution = ScopeResolver(FakeCatalog(TREE)).resolve(Scope())
    assert "ops.web.page_views" in fqns(resolution.tables)
    assert "main.marketing.leads" in fqns(resolution.tables)


def test_single_table_scope():
    resolution = ScopeResolver(FakeCatalog(TREE)).resolve(Scope("main", "sales", "orders", "amount"))
    assert resolution.tables == [TableRef("main", "sales", "orders", "TABLE")]


def test_metadata_failures_are_recorded_and_the_rest_still_resolves():
    catalog = FakeCatalog(TREE, failing={("ops",): "connection refused", ("main", "marketing"): "permission denied"})
    resolution = ScopeResolver(catalog).resolve(Scope())

    assert ("ops", None, "Couldn't list schemas: connection refused") in resolution.errors
    assert ("main", "marketing", "Couldn't list tables: permission denied") in resolution.errors
    assert "main.sales.orders" in fqns(resolution.tables)


def test_metadata_calls_are_memoised_across_resolutions():
    catalog = FakeCatalog(TREE, failing={("ops",): "down"})
    resolver = ScopeResolver(catalog)

    resolver.resolve(Scope())
    resolver.resolve(Scope())

    assert catalog.calls.count(("schemas", "main")) == 1
    assert catalog.calls.count(("schemas", "ops")) == 1
    assert catalog.calls.count(("tables", "main", "sales")) == 1
