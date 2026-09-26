from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pyspark.sql import types as T

from engine.quality.executor import DQExecutor, RunOptions
from engine.quality.families import family_of_spark
from engine.quality.rule_loader import parse_rule
from engine.quality.scope import ScopeResolver
from engine.quality.spark_scan import SparkTableScan
from engine.quality.templates import BindingError


pytestmark = pytest.mark.spark

NOW = datetime.now()

ORDERS_SCHEMA = T.StructType([
    T.StructField("order_id", T.LongType()),
    T.StructField("customer_id", T.LongType()),
    T.StructField("email", T.StringType()),
    T.StructField("amount", T.DecimalType(10, 2)),
    T.StructField("currency", T.StringType()),
    T.StructField("status_code", T.IntegerType()),
    T.StructField("country", T.StringType()),
    T.StructField("zip", T.StringType()),
    T.StructField("order_date", T.DateType()),
    T.StructField("updated_at", T.TimestampType()),
])

ORDERS = [
    (1, 1, "a@x", Decimal("10.00"), "USD", 1, "US", "123", date(2023, 12, 31), NOW - timedelta(hours=5)),
    (2, 2, "  ", Decimal("-5.00"), "usd", 2, "usa", "12a", date(2024, 1, 1), NOW - timedelta(hours=4)),
    (3, 3, "\t", Decimal("100.00"), "GBP", 3, "GB", "999", date(2024, 6, 1), NOW - timedelta(hours=3)),
    (3, None, None, None, None, 1, None, None, None, None),
    (5, 1, "b@y", Decimal("250.00"), "EUR", None, "D1", "1234", date(2025, 1, 1), NOW - timedelta(hours=2)),
]


class FrameCatalog:
    def __init__(self, frames):
        self.frames = frames

    def list_catalogs(self):
        return sorted({fqn.split(".")[0] for fqn in self.frames})

    def list_schemas(self, catalog):
        return sorted({fqn.split(".")[1] for fqn in self.frames if fqn.startswith(catalog + ".")})

    def list_tables(self, catalog, schema):
        prefix = f"{catalog}.{schema}."
        return [(fqn[len(prefix):], "TABLE") for fqn in self.frames if fqn.startswith(prefix)]

    def list_columns(self, catalog, schema, table):
        frame = self.frames[f"{catalog}.{schema}.{table}"]
        return [(f.name, family_of_spark(f.dataType)) for f in frame.schema.fields]


class FrameSource:
    def __init__(self, frames):
        self.frames = frames

    def open(self, table):
        return SparkTableScan(self.frames[table.fqn])


@pytest.fixture(scope="module")
def frames(spark):
    return {
        "main.sales.orders": spark.createDataFrame(ORDERS, ORDERS_SCHEMA),
        "main.sales.customers": spark.createDataFrame([(1,), (2,)], "id long"),
    }


def rule(name, template, column=None, **extra):
    scope = {"catalog": "main", "schema": "sales", "table": "orders"}

    if column:
        scope["column"] = column

    return parse_rule({"name": name, "template": template, "scope": scope, **extra}, rule_id=f"R_{name}")


def run_rules(frames, rules, **options):
    executor = DQExecutor(FrameSource(frames), ScopeResolver(FrameCatalog(frames)), RunOptions(**options))
    return {r.rule_name: r for r in executor.run(rules).results}


def counts(record):
    return record.pass_count, record.total_count


def test_every_row_template_computes_exact_counts(frames):
    results = run_rules(frames, [
        rule("customer_present", "not_null", "customer_id"),
        rule("email_filled", "not_blank", "email"),
        rule("amount_range", "in_range", "amount", params={"min": 0, "max": 100}),
        rule("amount_range_strict_nulls", "in_range", "amount", params={"min": 0, "max": 100}, nullPolicy="fail"),
        rule("recent_orders", "in_range", "order_date", params={"min": "2024-01-01"}),
        rule("currency_known", "allowed_values", "currency", params={"values": "USD, EUR", "matchCase": False}),
        rule("currency_exact", "allowed_values", "currency", params={"values": ["USD", "EUR"]}),
        rule("status_known", "allowed_values", "status_code", params={"values": "1, 2"}),
        rule("country_iso2", "regex_match", "country", params={"pattern": "^[A-Z]{2}$"}),
        rule("zip_three_digits", "regex_match", "zip", params={"pattern": r"\d{3}"}),
        rule("zip_has_digits", "regex_match", "zip", params={"pattern": r"\d{3}", "fullValue": False}),
        rule("amount_non_negative", "sql_row", "amount", params={"expression": "{column} IS NULL OR {column} >= 0"}),
    ])

    assert counts(results["customer_present"]) == (4, 5)
    assert results["customer_present"].status == "FAIL"
    assert counts(results["email_filled"]) == (2, 5)
    assert counts(results["amount_range"]) == (3, 5)
    assert counts(results["amount_range_strict_nulls"]) == (2, 5)
    assert counts(results["recent_orders"]) == (4, 5)
    assert counts(results["currency_known"]) == (4, 5)
    assert counts(results["currency_exact"]) == (3, 5)
    assert counts(results["status_known"]) == (4, 5)
    assert counts(results["country_iso2"]) == (3, 5)
    assert counts(results["zip_three_digits"]) == (3, 5)
    assert counts(results["zip_has_digits"]) == (4, 5)
    assert counts(results["amount_non_negative"]) == (4, 5)
    assert results["amount_non_negative"].metric_value == pytest.approx(0.8)


def test_aggregate_and_table_templates(frames):
    results = run_rules(frames, [
        rule("order_id_unique_exact", "unique_ratio", "order_id", params={"exact": True}),
        rule("order_id_unique_approx", "unique_ratio", "order_id"),
        rule("orders_fresh", "freshness_hours", "updated_at"),
        rule("orders_rows", "row_count"),
    ])

    assert results["order_id_unique_exact"].metric_value == pytest.approx(0.8)
    assert results["order_id_unique_approx"].metric_value == pytest.approx(0.8, abs=0.05)
    assert results["orders_fresh"].metric_value == pytest.approx(2.0, abs=0.1)
    assert results["orders_fresh"].status == "PASS"
    assert results["orders_rows"].metric_value == 5
    assert results["orders_rows"].total_count == 5


def test_row_filters_apply_to_every_level(frames):
    not_gbp = "currency <> 'GBP'"
    results = run_rules(frames, [
        rule("customer_present_non_gbp", "not_null", "customer_id", rowFilter=not_gbp),
        rule("usd_fresh", "freshness_hours", "updated_at", rowFilter="currency = 'USD'"),
        rule("status_one_rows", "row_count", rowFilter="status_code = 1"),
        rule("unique_non_gbp", "unique_ratio", "order_id", rowFilter=not_gbp, params={"exact": True}),
    ])

    # A NULL filter result excludes the row, so the currency-less row isn't counted.
    assert counts(results["customer_present_non_gbp"]) == (3, 3)
    assert results["usd_fresh"].metric_value == pytest.approx(5.0, abs=0.1)
    assert results["status_one_rows"].metric_value == 2
    assert results["unique_non_gbp"].metric_value == pytest.approx(1.0)


def test_referential_integrity_join(frames):
    results = run_rules(frames, [
        rule("order_customer_fk", "referential_integrity", "customer_id",
             params={"parentTable": "main.sales.customers", "parentColumn": "id"}),
    ])

    fk = results["order_customer_fk"]
    assert counts(fk) == (3, 4)
    assert fk.message == "1 key(s) missing from main.sales.customers"


def test_bad_expressions_error_alone_and_the_shared_scan_still_runs(frames):
    results = run_rules(frames, [
        rule("not_boolean", "sql_row", "amount", params={"expression": "{column} + 1"}),
        rule("unknown_column", "sql_row", "amount", params={"expression": "{column} > nonexistent_col"}),
        rule("bad_regex", "regex_match", "country", params={"pattern": "[A-Z"}),
        rule("bad_filter", "not_null", "order_id", rowFilter="nonexistent_col = 1"),
        rule("still_fine", "not_null", "order_id"),
    ])

    assert results["not_boolean"].status == "ERROR"
    assert "not BOOLEAN" in results["not_boolean"].message
    assert results["unknown_column"].status == "ERROR"
    assert "nonexistent_col" in results["unknown_column"].message
    assert results["bad_regex"].status == "ERROR"
    assert results["bad_regex"].message.startswith("Invalid regular expression")
    assert results["bad_filter"].status == "ERROR"
    assert counts(results["still_fine"]) == (5, 5)


def test_run_predicate_and_sampling(frames):
    filtered = run_rules(frames, [rule("customer_present", "not_null", "customer_id")], where="amount IS NOT NULL")
    assert counts(filtered["customer_present"]) == (4, 4)

    sampled = run_rules(
        frames,
        [rule("amount_range", "in_range", "amount", params={"min": 0, "max": 100})],
        sample_fraction=0.5,
        sample_seed=3,
    )
    assert sampled["amount_range"].sampled is True
    assert sampled["amount_range"].total_count <= 5


def test_chunked_passes_give_the_same_answers(frames):
    rules = [rule("present", "not_null", "*", rowFilter="order_id IS NOT NULL")]

    def by_column(**options):
        executor = DQExecutor(FrameSource(frames), ScopeResolver(FrameCatalog(frames)), RunOptions(**options))
        return {r.column: counts(r) for r in executor.run(rules).results}

    wide = by_column()
    chunked = by_column(max_exprs_per_pass=3)

    assert len(wide) == len(ORDERS_SCHEMA.fields)
    assert wide == chunked
    assert wide["customer_id"] == (4, 5)


def test_check_regex_and_boolean_directly(frames):
    scan = SparkTableScan(frames["main.sales.orders"])

    with pytest.raises(BindingError):
        scan.check_regex("(unclosed")

    scan.check_regex(r"^\d+$")
    scan.check_boolean("amount > 0")

    with pytest.raises(BindingError, match="not BOOLEAN"):
        scan.check_boolean("amount")
