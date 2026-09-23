from __future__ import annotations

import pytest

from engine.core.execution_context import ExecutionContext
from engine.rules.base_rule import BaseRule
from engine.rules.rule_registry import RuleRegistry
from engine.validation.validation_scorer import ValidationScorer


class _FakeRule(BaseRule):
    rule_id = "FAKE1"
    dimension = "Completeness"
    category = "Nulls"

    def validate(self, data, column_name, parameters, context):
        raise NotImplementedError


@pytest.fixture
def context() -> ExecutionContext:
    return ExecutionContext(project_name="p", run_timestamp="t")


@pytest.fixture
def rule_registry() -> RuleRegistry:
    registry = RuleRegistry()
    registry.register(_FakeRule)
    return registry


@pytest.fixture
def scorer(context, rule_registry) -> ValidationScorer:
    return ValidationScorer(context=context, rule_registry=rule_registry)


def test_rule_score_is_the_pass_ratio(scorer):
    assert scorer.calculate_rule_score(total_rows=100, invalid_count=25) == 0.75


def test_rule_score_defaults_to_perfect_when_there_are_no_rows(scorer):
    assert scorer.calculate_rule_score(total_rows=0, invalid_count=0) == 1.0


def test_get_dimension_resolves_a_registered_rule(scorer):
    assert scorer.get_dimension("FAKE1") == "Completeness"


def test_get_dimension_defaults_to_other_for_an_unregistered_rule(scorer):
    assert scorer.get_dimension("NOT_REGISTERED") == "Other"


def test_get_category_resolves_a_registered_rule(scorer):
    assert scorer.get_category("FAKE1") == "Nulls"


def test_get_category_defaults_to_other_for_an_unregistered_rule(scorer):
    assert scorer.get_category("NOT_REGISTERED") == "Other"


def test_add_rule_score_groups_scores_by_dimension(scorer):
    dimension_scores: dict[str, list[float]] = {}
    scorer.add_rule_score(dimension_scores, "FAKE1", 0.9)
    scorer.add_rule_score(dimension_scores, "FAKE1", 0.7)

    assert dimension_scores == {"Completeness": [0.9, 0.7]}


def test_calculate_dimension_scores_averages_each_dimension(scorer):
    result = scorer.calculate_dimension_scores(
        {"Completeness": [1.0, 0.5], "Conformity": [0.8]}
    )
    assert result == {"Completeness": 0.75, "Conformity": 0.8}


def test_calculate_dimension_scores_defaults_an_empty_dimension_to_perfect(scorer):
    assert scorer.calculate_dimension_scores({"Completeness": []}) == {"Completeness": 1.0}


def test_calculate_overall_score_averages_dimensions(scorer):
    assert scorer.calculate_overall_score({"A": 1.0, "B": 0.5}) == 0.75


def test_calculate_overall_score_defaults_to_perfect_when_there_are_no_dimensions(scorer):
    assert scorer.calculate_overall_score({}) == 1.0


def test_calculate_scores_combines_dimension_and_overall(scorer):
    dimension_scores, overall = scorer.calculate_scores({"A": [1.0, 0.0]})
    assert dimension_scores == {"A": 0.5}
    assert overall == 0.5
