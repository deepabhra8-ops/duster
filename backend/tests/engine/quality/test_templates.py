from __future__ import annotations

import pytest

from engine.quality import families as F
from engine.quality.models import RuleValidationError
from engine.quality.templates import (
    REGISTRY,
    BindingError,
    BuildContext,
    describe_templates,
    get_template,
    parse_parent_table,
)


FRONTEND_TEMPLATES = {
    "not_null", "not_blank", "in_range", "allowed_values", "regex_match",
    "unique_ratio", "freshness_hours", "row_count", "referential_integrity", "sql_row",
}


def build(name, params, family=F.NUMERIC, column="`c`", value=None, rows="1"):
    template = get_template(name)
    normalized = template.normalize(params)
    return template.build(BuildContext(params=normalized, family=family, column=column, value=value or column, rows=rows))


def test_registry_covers_every_template_the_editor_offers():
    assert set(REGISTRY) == FRONTEND_TEMPLATES


def test_unknown_template_is_a_validation_error():
    with pytest.raises(RuleValidationError, match="Unknown template"):
        get_template("no_such_template")


def test_describe_templates_exposes_metric_and_default_threshold():
    by_name = {t["name"]: t for t in describe_templates()}

    assert by_name["in_range"]["thresholdMetric"] == "pass_rate"
    assert by_name["freshness_hours"]["thresholdMetric"] == "value"
    assert by_name["freshness_hours"]["defaultThreshold"] == {"metric": "value", "op": "<=", "value": 24.0}
    assert by_name["row_count"]["needsColumn"] is False


@pytest.mark.parametrize("name", sorted(FRONTEND_TEMPLATES))
def test_every_template_rejects_unknown_parameters(name):
    with pytest.raises(RuleValidationError, match="does not take"):
        get_template(name).normalize({"surprise": 1})


def test_not_null_and_not_blank():
    assert build("not_null", {}) == "`c` IS NOT NULL"
    assert build("not_blank", {}, family=F.STRING) == r"`c` IS NOT NULL AND `c` RLIKE '\\S'"


def test_in_range_numeric_inclusive_and_exclusive():
    assert build("in_range", {"min": "0", "max": "250000"}) == "`c` >= 0 AND `c` <= 250000"
    assert build("in_range", {"min": 0, "max": 1.5, "boundsInclusive": False}) == "`c` > 0 AND `c` < 1.5"
    assert build("in_range", {"max": 10}) == "`c` <= 10"


def test_in_range_temporal_bounds_render_date_literals():
    sql = build("in_range", {"min": "2020-01-01", "max": "2030-12-31T00:00:00"}, family=F.TEMPORAL)
    assert sql == "`c` >= DATE'2020-01-01' AND `c` <= TIMESTAMP'2030-12-31 00:00:00'"


def test_in_range_bounds_that_do_not_fit_the_column_are_binding_errors():
    with pytest.raises(BindingError, match="is a number, but the column is temporal"):
        build("in_range", {"min": 0, "max": 100}, family=F.TEMPORAL)

    with pytest.raises(BindingError, match="is a date"):
        build("in_range", {"min": "2020-01-01"}, family=F.NUMERIC)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "min, a max, or both"),
        ({"min": 10, "max": 1}, "greater than max"),
        ({"min": "2024-02-01", "max": "2024-01-01"}, "greater than max"),
        ({"min": 1, "max": "2024-01-01"}, "both be numbers"),
        ({"min": "soon"}, "number or an ISO date"),
        ({"min": 1, "boundsInclusive": "yes"}, "true or false"),
    ],
)
def test_in_range_parameter_validation(params, message):
    with pytest.raises(RuleValidationError, match=message):
        get_template("in_range").normalize(params)


def test_in_range_accepts_mixed_date_and_timestamp_bounds():
    normalized = get_template("in_range").normalize({"min": "2024-01-01", "max": "2024-01-01T12:00:00"})
    assert normalized["min"] == "2024-01-01"


def test_allowed_values_from_comma_string_for_strings_and_numbers():
    assert build("allowed_values", {"values": "USD, EUR, USD"}, family=F.STRING) == "`c` IN ('USD', 'EUR')"
    assert build("allowed_values", {"values": ["1", "2.5"]}, family=F.NUMERIC) == "`c` IN (1, 2.5)"


def test_allowed_values_ignore_case_lowers_both_sides():
    sql = build("allowed_values", {"values": "USD, usd, Eur", "matchCase": False}, family=F.STRING)
    assert sql == "lower(`c`) IN ('usd', 'eur')"


def test_allowed_values_non_numeric_value_on_numeric_column_is_a_binding_error():
    with pytest.raises(BindingError, match="not a number"):
        build("allowed_values", {"values": "USD"}, family=F.NUMERIC)


def test_allowed_values_needs_at_least_one_value():
    with pytest.raises(RuleValidationError, match="at least one"):
        get_template("allowed_values").normalize({"values": " , "})


def test_regex_full_value_is_anchored_and_contains_is_not():
    assert build("regex_match", {"pattern": "^[A-Z]{2}$"}, family=F.STRING) == "`c` RLIKE '^(?:^[A-Z]{2}$)$'"
    assert build("regex_match", {"pattern": r"\d", "fullValue": False}, family=F.STRING) == r"`c` RLIKE '\\d'"


def test_unique_ratio_approximate_and_exact():
    approx = build("unique_ratio", {}, value="`c`")
    assert "approx_count_distinct(`c`, 0.05D)" in approx
    assert approx.startswith("CASE WHEN count(`c`) = 0 THEN NULL")

    exact = build("unique_ratio", {"exact": True})
    assert "count(DISTINCT `c`)" in exact
    assert get_template("unique_ratio").separate_pass({"exact": True}) is True
    assert get_template("unique_ratio").separate_pass({"exact": False}) is False


def test_unique_ratio_rejects_an_out_of_range_rsd():
    with pytest.raises(RuleValidationError, match="maxRsd"):
        get_template("unique_ratio").normalize({"maxRsd": 0.5})


def test_freshness_and_row_count_use_the_filtered_value_and_rows():
    assert build("freshness_hours", {}, family=F.TEMPORAL, value="CASE WHEN f THEN `c` END") == (
        "(unix_timestamp(current_timestamp()) - unix_timestamp(max(CASE WHEN f THEN `c` END))) / 3600D"
    )
    assert build("row_count", {}, column=None, rows="CASE WHEN f THEN 1 END") == "count(CASE WHEN f THEN 1 END)"


def test_freshness_only_measures_against_current_timestamp():
    with pytest.raises(RuleValidationError, match="measuredAgainst"):
        get_template("freshness_hours").normalize({"measuredAgainst": "now() - interval 1 day"})


def test_sql_row_substitutes_the_quoted_column():
    assert build("sql_row", {"expression": "{column} IS NULL OR {column} >= 0"}) == "(`c` IS NULL OR `c` >= 0)"


def test_sql_row_refuses_subqueries():
    with pytest.raises(RuleValidationError, match="subquery"):
        get_template("sql_row").normalize({"expression": "{column} IN (SELECT id FROM x)"})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("main.sales.customers", ("main", "sales", "customers")),
        ("sales.customers", (None, "sales", "customers")),
        ("prod.pg.sales.customers", ("prod.pg", "sales", "customers")),
    ],
)
def test_parse_parent_table(value, expected):
    assert parse_parent_table(value) == expected


@pytest.mark.parametrize("value", ["customers", "main..customers", "main.sales.*"])
def test_parse_parent_table_rejects_bad_references(value):
    with pytest.raises(RuleValidationError):
        parse_parent_table(value)
