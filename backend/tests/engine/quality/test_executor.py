from __future__ import annotations

import threading

import pytest

from engine.quality.executor import DQExecutor, RunOptions, with_scope
from engine.quality.models import Scope
from engine.quality.rule_loader import parse_rule
from engine.quality.scope import ScopeResolver
from utils.job_cancellation import JobCancelledError

from tests.engine.quality.fakes import FakeCatalog, FakeScan, FakeSource, sequential


COLUMNS = [("order_id", "numeric"), ("order_amount", "numeric"), ("raw_amount", "string"), ("updated_at", "temporal")]
TREE = {"main": {"sales": {"orders": COLUMNS, "refunds": COLUMNS}}}


def rule(name, template, scope=None, **extra):
    return parse_rule({"name": name, "template": template, "scope": scope or {}, **extra}, rule_id=f"R_{name}")


def executor(scans, options=None, broken=None, tree=TREE, failing=None, **kwargs):
    return DQExecutor(
        FakeSource(scans, broken=broken),
        ScopeResolver(FakeCatalog(tree, failing=failing)),
        options or RunOptions(),
        parallel=sequential,
        **kwargs,
    )


def by_target(results):
    return {(r.table, r.column, r.rule_name): r for r in results}


def test_row_rule_counts_become_pass_rates_and_statuses():
    passes = {"order_id": 100, "order_amount": 95}

    def answer(sql):
        return next(n for column, n in passes.items() if f"`{column}`" in sql)

    scan = FakeScan(COLUMNS, answer=answer, rows=100)
    rules = [rule("present", "not_null", {"table": "orders", "column": "order_*"}, threshold={"value": 0.99})]

    outcome = executor({"main.sales.orders": scan}).run(rules)
    results = by_target(outcome.results)

    ok = results[("orders", "order_id", "present")]
    assert (ok.status, ok.total_count, ok.pass_count, ok.fail_count, ok.metric_value) == ("PASS", 100, 100, 0, 1.0)

    bad = results[("orders", "order_amount", "present")]
    assert (bad.status, bad.fail_count, bad.metric_value) == ("FAIL", 5, 0.95)
    assert len(scan.aggregates) == 1


def test_warn_severity_and_skips_are_recorded():
    scan = FakeScan(COLUMNS, answer=lambda sql: 50, rows=100)
    rules = [rule("range", "in_range", {"table": "orders", "column": "*_amount"}, params={"min": 0}, severity="warn")]

    results = executor({"main.sales.orders": scan}).run(rules).results
    statuses = sorted((r.column, r.status, r.message) for r in results)

    assert statuses == [
        ("order_amount", "WARN", None),
        ("raw_amount", "SKIPPED", "type string not in [numeric, temporal]"),
    ]


def test_empty_table_is_no_data_but_row_count_still_judged():
    scan = FakeScan(COLUMNS, answer=lambda sql: 0, rows=0)
    rules = [rule("present", "not_null", {"table": "orders", "column": "order_id"}), rule("rows", "row_count", {"table": "orders"})]

    results = by_target(executor({"main.sales.orders": scan}).run(rules).results)

    assert results[("orders", "order_id", "present")].status == "NO_DATA"
    assert results[("orders", "order_id", "present")].message == "Table has no rows"
    assert results[("orders", None, "rows")].status == "FAIL"
    assert results[("orders", None, "rows")].metric_value == 0.0


def test_aggregate_metric_values_and_null_is_no_data():
    def answer(sql):
        return None if "approx_count_distinct" in sql else 31.2

    scan = FakeScan(COLUMNS, answer=answer, rows=10)
    rules = [
        rule("unique", "unique_ratio", {"table": "orders", "column": "order_id"}),
        rule("fresh", "freshness_hours", {"table": "orders", "column": "updated_at"}),
    ]

    results = by_target(executor({"main.sales.orders": scan}).run(rules).results)

    assert results[("orders", "order_id", "unique")].status == "NO_DATA"
    assert results[("orders", "order_id", "unique")].message == "No non-null values to measure"
    fresh = results[("orders", "updated_at", "fresh")]
    assert (fresh.status, fresh.metric_value, fresh.total_count, fresh.pass_count) == ("FAIL", 31.2, 10, None)


def test_bad_user_sql_errors_only_its_own_binding():
    scan = FakeScan(COLUMNS, rows=10, bad_sql=("nonexistent",))
    rules = [
        rule("custom", "sql_row", {"table": "orders", "column": "order_id"}, params={"expression": "{column} > nonexistent"}),
        rule("present", "not_null", {"table": "orders", "column": "order_id"}),
    ]

    results = by_target(executor({"main.sales.orders": scan}).run(rules).results)

    assert results[("orders", "order_id", "custom")].status == "ERROR"
    assert "nonexistent" in results[("orders", "order_id", "custom")].message
    assert results[("orders", "order_id", "present")].status == "PASS"


def test_invalid_regex_errors_its_binding_before_the_scan():
    scan = FakeScan([("code", "string")], rows=10)
    rules = [rule("fmt", "regex_match", {"table": "orders"}, params={"pattern": "[A-Z"})]

    results = executor({"main.sales.orders": scan}).run(rules).results

    assert [(r.status, r.message) for r in results if r.table == "orders"] == [
        ("ERROR", "Invalid regular expression: Unclosed character class"),
    ]
    assert scan.aggregates == []


def test_a_failing_pass_errors_its_members_with_a_short_message():
    scan = FakeScan(COLUMNS, rows=10, fail_aggregate="count_if")
    rules = [rule("present", "not_null", {"table": "orders", "column": "order_id"})]

    result = executor({"main.sales.orders": scan}).run(rules).results[0]

    assert result.status == "ERROR"
    assert result.message == "org.apache.spark.SparkException: boom"


def test_a_table_that_cannot_be_opened_errors_every_rule_on_it_and_others_continue():
    rules = [rule("present", "not_null", {"table": "*", "column": "order_id"})]
    scans = {"main.sales.orders": FakeScan(COLUMNS, rows=10)}

    results = executor(scans, broken={"main.sales.refunds": "INSUFFICIENT_PERMISSIONS: no SELECT"}).run(rules).results
    statuses = {(r.table, r.status) for r in results}

    assert statuses == {("orders", "PASS"), ("refunds", "ERROR")}
    assert next(r for r in results if r.table == "refunds").message == "INSUFFICIENT_PERMISSIONS: no SELECT"


def test_unreachable_catalog_becomes_error_results():
    tree = {**TREE, "ops": {"web": {}}}
    rules = [rule("present", "not_null", {"column": "order_id"})]
    scans = {fqn: FakeScan(COLUMNS, rows=1) for fqn in ("main.sales.orders", "main.sales.refunds")}

    results = executor(scans, tree=tree, failing={("ops",): "connection refused"}).run(rules).results
    errors = [r for r in results if r.status == "ERROR"]

    assert [(r.catalog, r.schema, r.table, r.message) for r in errors] == [
        ("ops", None, None, "Couldn't list schemas: connection refused"),
    ]


def test_run_predicate_applies_to_every_table_and_is_recorded():
    scan = FakeScan(COLUMNS, rows=10)
    options = RunOptions(where="event_date = current_date()")
    results = executor({"main.sales.orders": scan}, options=options).run(
        [rule("present", "not_null", {"table": "orders", "column": "order_id"})]
    ).results

    assert scan.restricted == ["event_date = current_date()"]
    assert results[0].where_clause == "event_date = current_date()"


def test_run_predicate_that_does_not_fit_a_table_errors_that_table():
    options = RunOptions(where="missing_col = 1")
    result = executor({"main.sales.orders": FakeScan(COLUMNS)}, options=options).run(
        [rule("present", "not_null", {"table": "orders", "column": "order_id"})]
    ).results[0]

    assert result.status == "ERROR"
    assert result.message.startswith("Run predicate doesn't apply to this table: [UNRESOLVED_COLUMN]")


def test_sampled_passes_are_flagged_and_existence_checks_stay_full():
    scan = FakeScan(COLUMNS, answer=lambda sql: 10, rows=10)
    options = RunOptions(sample_fraction=0.1, sample_seed=7)
    rules = [
        rule("range", "in_range", {"table": "orders", "column": "order_amount"}, params={"min": 0}),
        rule("present", "not_null", {"table": "orders", "column": "order_id"}),
    ]

    results = by_target(executor({"main.sales.orders": scan}, options=options).run(rules).results)

    assert sorted(sample for _, sample in scan.aggregates if sample) == [(0.1, 7)]
    assert results[("orders", "order_amount", "range")].sampled is True
    assert results[("orders", "order_amount", "range")].sample_fraction == 0.1
    assert results[("orders", "order_id", "present")].sampled is False


def test_referential_integrity_counts_missing_keys():
    scans = {
        "main.sales.orders": FakeScan(COLUMNS, coverage=(1000, 990)),
        "main.sales.customers": FakeScan([("id", "numeric")]),
    }
    tree = {"main": {"sales": {"orders": COLUMNS, "customers": [("id", "numeric")]}}}
    fk = rule(
        "fk",
        "referential_integrity",
        {"table": "orders", "column": "order_id"},
        params={"parentTable": "sales.customers", "parentColumn": "id"},
    )

    source_executor = executor(scans, tree=tree)
    result = source_executor.run([fk]).results[0]

    assert (result.status, result.total_count, result.pass_count, result.fail_count) == ("FAIL", 1000, 990, 10)
    assert result.message == "10 key(s) missing from main.sales.customers"
    assert "main.sales.customers" in source_executor.source.opened


def test_progress_is_reported_per_table():
    seen = []
    scans = {fqn: FakeScan(COLUMNS, rows=1) for fqn in ("main.sales.orders", "main.sales.refunds")}

    executor(scans, progress=lambda done, total: seen.append((done, total))).run(
        [rule("present", "not_null", {"column": "order_id"})]
    )

    assert seen == [(0, 2), (1, 2), (2, 2)]


def test_cancellation_stops_the_run():
    event = threading.Event()
    event.set()

    with pytest.raises(JobCancelledError):
        executor({"main.sales.orders": FakeScan(COLUMNS)}, cancel_event=event).run(
            [rule("present", "not_null", {"table": "orders", "column": "order_id"})]
        )


def test_run_scope_overrides_rule_scope():
    rules = [rule("present", "not_null", {"catalog": "elsewhere"})]
    scoped = with_scope(rules, Scope("main", "sales", "orders", "order_id"))

    assert scoped[0].scope.catalog == "main"
    assert rules[0].scope.catalog == "elsewhere"
    assert with_scope(rules, None) == rules
