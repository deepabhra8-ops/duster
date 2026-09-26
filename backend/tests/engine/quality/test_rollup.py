from __future__ import annotations

import pytest

from engine.quality import rollup


def result(status, catalog="main", schema="sales", table="orders", column="c", passed=None, total=None, **extra):
    return {
        "rule_id": extra.pop("rule_id", "R001"),
        "rule_level": extra.pop("rule_level", "row"),
        "severity": extra.pop("severity", "error"),
        "dimension": extra.pop("dimension", "completeness"),
        "status": status,
        "catalog": catalog,
        "schema": schema,
        "table": table,
        "column": column,
        "pass_count": passed,
        "total_count": total,
        **extra,
    }


RESULTS = [
    # A big table, nearly perfect.
    result("PASS", table="orders", passed=9990, total=10000),
    result("FAIL", table="orders", column="d", passed=9000, total=10000, rule_id="R002"),
    # A tiny lookup table, badly broken.
    result("FAIL", table="lookup", passed=1, total=10, rule_id="R003"),
    # Aggregate metrics count only through their status.
    result("WARN", table="orders", column="u", rule_level="aggregate", severity="warn", dimension="uniqueness", rule_id="R004"),
    result("NO_DATA", table="refunds", passed=0, total=0),
    result("SKIPPED", table="orders", column="raw"),
    result("ERROR", catalog="ops", schema=None, table=None, column=None, rule_id="R005"),
]


def test_row_weighted_vs_table_average():
    kpis = rollup.kpis(RESULTS)

    # micro: (9990 + 9000 + 1) / (10000 + 10000 + 10)
    assert kpis["rowWeighted"] == pytest.approx(18991 / 20010)
    # macro: mean of orders (18990/20000) and lookup (1/10); refunds has no rows to score.
    assert kpis["tableAverage"] == pytest.approx((18990 / 20000 + 0.1) / 2)
    assert kpis["thresholdsMet"] == 1
    assert kpis["thresholdsEvaluated"] == 6
    assert kpis["resultCount"] == 7


def test_status_counts_include_attention_and_all():
    counts = rollup.status_counts(RESULTS)

    assert counts["FAIL"] == 2 and counts["SKIPPED"] == 1 and counts["PASS"] == 1
    assert counts["attention"] == 5
    assert counts["ALL"] == 7


def test_tree_rolls_up_catalog_schema_table():
    tree = rollup.summarize(RESULTS)["tree"]
    main = next(node for node in tree if node["name"] == "main")
    ops = next(node for node in tree if node["name"] == "ops")

    assert [node["name"] for node in tree] == ["main", "ops"]  # FAIL sorts before ERROR
    assert ops == {
        "name": "ops", "kind": "catalog", "rowWeighted": None, "simpleAverage": None,
        "bindings": 1, "notPassing": 1, "worstStatus": "ERROR", "children": [],
    }

    sales = main["children"][0]
    tables = {node["name"]: node for node in sales["children"]}

    assert tables["orders"]["rowWeighted"] == pytest.approx(18990 / 20000)
    assert tables["orders"]["simpleAverage"] == pytest.approx((0.999 + 0.9) / 2)
    assert tables["orders"]["bindings"] == 3  # the skipped binding isn't evaluated
    assert tables["orders"]["notPassing"] == 2
    assert tables["refunds"]["worstStatus"] == "NO_DATA"
    assert "children" not in tables["orders"]
    assert sales["simpleAverage"] == pytest.approx((18990 / 20000 + 0.1) / 2)


def test_dimensions_and_worst_severity():
    summary = rollup.summarize(RESULTS)

    assert summary["dimensions"] == [
        {"dimension": "completeness", "met": 1, "total": 5},
        {"dimension": "uniqueness", "met": 0, "total": 1},
    ]
    assert summary["worstSeverity"] == {"severity": "error", "bindings": 2, "rules": 2, "errors": 1}


def test_worst_severity_when_nothing_fails():
    assert rollup.summarize([result("PASS", passed=1, total=1)])["worstSeverity"]["severity"] is None


def test_worst_status_ignores_skipped_unless_that_is_all_there_is():
    assert rollup.worst_status(["PASS", "SKIPPED"]) == "PASS"
    assert rollup.worst_status(["SKIPPED"]) == "SKIPPED"
    assert rollup.worst_status([]) is None


def test_rule_status_counts():
    assert rollup.rule_status_counts(RESULTS)["R001"] == {"PASS": 1, "NO_DATA": 1, "SKIPPED": 1}
