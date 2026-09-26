from __future__ import annotations

from datetime import date, datetime

import pytest

from engine.quality.models import RuleValidationError
from engine.quality.sql_text import (
    check_sql_fragment,
    display_fqn,
    number_literal,
    parse_number,
    parse_temporal,
    quote_ident,
    string_literal,
    temporal_literal,
)


def test_quote_ident_doubles_embedded_backticks():
    assert quote_ident("amount") == "`amount`"
    assert quote_ident("we`ird") == "`we``ird`"


def test_display_fqn_only_quotes_names_that_need_it():
    assert display_fqn("main", "sales", "orders") == "main.sales.orders"
    assert display_fqn("prod pg", "sales", "order-lines") == "`prod pg`.sales.`order-lines`"


def test_string_literal_escapes_quotes_and_backslashes_for_spark():
    assert string_literal("USD") == "'USD'"
    assert string_literal("it's") == "'it\\'s'"
    # A regex backslash is doubled so Spark's unescaping hands the engine ^\d+$ back.
    assert string_literal(r"^\d+$") == r"'^\\d+$'"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0"), (250000, "250000"), (2.5, "2.5"), (100.0, "100"), (-3, "-3"), (1e-05, "1e-05")],
)
def test_number_literal(value, expected):
    assert number_literal(value) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_number_literal_rejects_non_finite_and_booleans(value):
    with pytest.raises(RuleValidationError):
        number_literal(value)


def test_parse_number_accepts_numeric_strings_only():
    assert parse_number("250000") == 250000
    assert parse_number(" 2.5 ") == 2.5
    assert parse_number("2024-01-01") is None
    assert parse_number("") is None
    assert parse_number(False) is None


def test_temporal_parsing_and_literals():
    assert temporal_literal(parse_temporal("2024-01-31")) == "DATE'2024-01-31'"
    assert parse_temporal("2024-01-31T10:00:00") == datetime(2024, 1, 31, 10, 0)
    assert temporal_literal(datetime(2024, 1, 31, 10, 0)) == "TIMESTAMP'2024-01-31 10:00:00'"
    # Offsets are normalised to UTC, the Spark session's time zone.
    assert parse_temporal("2024-01-31T10:00:00+02:00") == datetime(2024, 1, 31, 8, 0)
    assert parse_temporal("next tuesday") is None
    assert isinstance(parse_temporal("2024-02-29"), date)


@pytest.mark.parametrize(
    "fragment",
    ["a = 1; DROP TABLE t", "id IN (SELECT id FROM other)", "   "],
)
def test_check_sql_fragment_refuses_statements_and_subqueries(fragment):
    with pytest.raises(RuleValidationError):
        check_sql_fragment(fragment, "rowFilter")


def test_check_sql_fragment_trims_a_plain_predicate():
    assert check_sql_fragment("  order_status <> 'cancelled' ", "rowFilter") == "order_status <> 'cancelled'"
