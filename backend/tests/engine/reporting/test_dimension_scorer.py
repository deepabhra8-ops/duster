"""Unit tests for DimensionScorer: pure scoring math for the dimension report."""
from __future__ import annotations

import polars as pl
import pytest

from engine.reporting.dimension_scorer import DimensionScorer


@pytest.fixture
def scorer() -> DimensionScorer:
    return DimensionScorer()


@pytest.mark.parametrize(
    "value, expected",
    [
        (0.5, 0.5),
        (-1, 0.0),
        (2, 1.0),
        ("not a number", 0.0),
        (None, 0.0),
    ],
)
def test_safe_score_clamps_to_zero_one(scorer, value, expected):
    assert scorer.safe_score(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (5, 5),
        ("7", 7),
        ("not a number", 0),
        (None, 0),
    ],
)
def test_safe_integer_defaults_invalid_values_to_zero(scorer, value, expected):
    assert scorer.safe_integer(value) == expected


def test_format_score_renders_as_a_percentage(scorer):
    assert scorer.format_score(0.937) == "93.7%"


def test_score_bar_is_fully_filled_at_one(scorer):
    assert scorer.score_bar(1.0, width=10) == "█" * 10


def test_score_bar_is_fully_empty_at_zero(scorer):
    assert scorer.score_bar(0.0, width=10) == "░" * 10


def test_score_bar_clamps_out_of_range_scores(scorer):
    assert scorer.score_bar(5.0, width=4) == "████"
    assert scorer.score_bar(-5.0, width=4) == "░░░░"


def test_overall_score_averages_the_score_column(scorer):
    dataframe = pl.DataFrame({"Score": [1.0, 0.5, 0.0]})
    assert scorer.overall_score(dataframe) == 0.5


def test_overall_score_defaults_to_perfect_for_an_empty_dataframe(scorer):
    assert scorer.overall_score(pl.DataFrame()) == 1.0


def test_overall_score_defaults_to_perfect_when_there_is_no_score_column(scorer):
    assert scorer.overall_score(pl.DataFrame({"Other": [1, 2]})) == 1.0


@pytest.mark.parametrize(
    "score, expected_bucket",
    [
        (1.0, "good"),
        (0.95, "good"),
        (0.94, "warning"),
        (0.80, "warning"),
        (0.79, "poor"),
        (0.0, "poor"),
    ],
)
def test_bucket_grades_scores_at_the_configured_thresholds(scorer, score, expected_bucket):
    assert scorer.bucket(score) == expected_bucket
