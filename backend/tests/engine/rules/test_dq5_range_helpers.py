"""Unit tests for DQ5RangeRule's pure static helpers (parsing/comparison logic used inside
its per-value Spark UDF) - these run identically with or without Spark, so they're tested
directly rather than through a full DataFrame.
"""
from __future__ import annotations

import pytest

from engine.rules.dq5_range import DQ5RangeRule


@pytest.mark.parametrize("value", [None, "", "   ", float("nan")])
def test_is_null_like_recognizes_null_blank_and_nan(value):
    assert DQ5RangeRule._is_null_like(value) is True


@pytest.mark.parametrize("value", ["0", "abc", 0, False])
def test_is_null_like_does_not_treat_falsy_non_null_values_as_null(value):
    assert DQ5RangeRule._is_null_like(value) is False


def test_safe_strip_returns_empty_string_for_null_like_values():
    assert DQ5RangeRule._safe_strip(None) == ""


def test_safe_strip_strips_whitespace():
    assert DQ5RangeRule._safe_strip("  hello  ") == "hello"


def test_safe_float_parses_numeric_strings():
    assert DQ5RangeRule._safe_float("42.5") == 42.5


def test_safe_float_returns_none_for_non_numeric_strings():
    assert DQ5RangeRule._safe_float("not a number") is None


def test_safe_date_parse_parses_a_recognizable_date_string():
    parsed = DQ5RangeRule._safe_date_parse("2024-01-15")
    assert (parsed.year, parsed.month, parsed.day) == (2024, 1, 15)


def test_safe_date_parse_returns_none_for_an_unparseable_string():
    assert DQ5RangeRule._safe_date_parse("not a date") is None


def test_range_notes_describes_a_bounded_range():
    assert DQ5RangeRule._range_notes("1", "10") == "Value must be between 1 and 10"


def test_range_notes_describes_a_minimum_only_range():
    assert DQ5RangeRule._range_notes("1", "") == "Value must be at least 1"


def test_range_notes_describes_a_maximum_only_range():
    assert DQ5RangeRule._range_notes("", "10") == "Value must be at most 10"
