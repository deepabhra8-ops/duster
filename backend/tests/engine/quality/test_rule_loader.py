from __future__ import annotations

import pytest

from engine.quality.models import RuleValidationError, Scope, Threshold
from engine.quality.rule_loader import effective_dimension, effective_families, parse_rule, parse_scope
from engine.quality.templates import get_template


def payload(**overrides):
    base = {
        "name": "amounts_in_range",
        "template": "in_range",
        "params": {"min": 0, "max": 250000},
        "threshold": {"metric": "pass_rate", "op": ">=", "value": 0.99},
        "severity": "error",
        "scope": {"catalog": "main", "schema": "sales*", "table": "*", "column": "*_amount"},
    }
    base.update(overrides)
    return base


def test_parse_rule_builds_a_rule_instance():
    rule = parse_rule(payload(rowFilter=" order_status <> 'cancelled' "), rule_id="R021", version=3)

    assert rule.rule_id == "R021"
    assert rule.version == 3
    assert rule.threshold == Threshold("pass_rate", ">=", 0.99)
    assert rule.scope == Scope("main", "sales*", "*", "*_amount")
    assert rule.row_filter == "order_status <> 'cancelled'"
    assert rule.params == {"min": 0, "max": 250000, "boundsInclusive": True}


def test_defaults_come_from_the_template():
    rule = parse_rule({"name": "orders_fresh", "template": "freshness_hours"})

    assert rule.threshold == Threshold("value", "<=", 24.0)
    assert rule.severity == "error"
    assert rule.scope.table_types == ("MANAGED", "EXTERNAL")
    assert effective_dimension(rule, get_template("freshness_hours")) == "timeliness"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "1bad"}, "name must start with a letter"),
        ({"name": "has space"}, "name must start with a letter"),
        ({"template": "nope"}, "Unknown template"),
        ({"severity": "critical"}, "severity must be one of"),
        ({"nullPolicy": "maybe"}, "nullPolicy must be one of"),
        ({"threshold": {"metric": "value", "op": ">=", "value": 1}}, "measured by pass_rate"),
        ({"threshold": {"metric": "pass_rate", "op": "~", "value": 1}}, "threshold.op"),
        ({"threshold": {"metric": "pass_rate", "op": ">=", "value": 99}}, "at most 1"),
        ({"weight": 0}, "weight"),
        ({"enabled": "yes"}, "enabled"),
        ({"rowFilter": "x = 1; drop table t"}, "single expression"),
        ({"dimension": "vibes"}, "dimension must be one of"),
        ({"appliesTo": ["string"]}, "only applies to"),
        ({"appliesTo": ["numbers"]}, "Unknown type"),
        ({"description": "x" * 1001}, "description"),
    ],
)
def test_parse_rule_rejects_invalid_input(overrides, message):
    with pytest.raises(RuleValidationError, match=message):
        parse_rule(payload(**overrides))


def test_applies_to_narrows_the_template_families():
    rule = parse_rule(payload(appliesTo=["numeric"]))
    assert effective_families(rule, get_template("in_range")) == frozenset({"numeric"})

    any_rule = parse_rule(payload(template="not_null", params={}, threshold=None, appliesTo=["string"]))
    assert effective_families(any_rule, get_template("not_null")) == frozenset({"string"})


def test_dimension_override():
    rule = parse_rule(payload(template="sql_row", params={"expression": "{column} > 0"}, dimension="Accuracy"))
    assert effective_dimension(rule, get_template("sql_row")) == "accuracy"


def test_parse_scope_normalises_globs_types_and_excludes():
    scope = parse_scope({
        "level": "schema",
        "catalog": " main ",
        "schema": "",
        "exclude": ["main.sales_tmp.*", "main.sales_tmp.*", " *.*._bak_* "],
        "tableTypes": ["managed", "VIEW"],
    })

    assert scope.catalog == "main"
    assert scope.schema == "*"
    assert scope.exclude == ("main.sales_tmp.*", "*.*._bak_*")
    assert scope.table_types == ("MANAGED", "VIEW")
    assert scope.level == "schema"


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ({"tableTypes": []}, "at least one"),
        ({"tableTypes": ["TEMP"]}, "drawn from"),
        ({"exclude": "main.*"}, "list of patterns"),
        ({"level": "galaxy"}, "scope.level"),
        ({"catalog": 5}, "must be a string"),
    ],
)
def test_parse_scope_rejects_invalid_scopes(scope, message):
    with pytest.raises(RuleValidationError, match=message):
        parse_scope(scope)
