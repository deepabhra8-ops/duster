from __future__ import annotations

import pytest

from engine.validation.failure_policy import FailurePolicy


@pytest.fixture
def policy() -> FailurePolicy:
    return FailurePolicy()


@pytest.mark.parametrize("rule_id", ["DQ10", "DQ11"])
def test_uniqueness_and_custom_rules_do_not_propagate(policy, rule_id):
    assert policy.should_propagate(rule_id) is False


@pytest.mark.parametrize(
    "rule_id", ["DQ1", "DQ2", "DQ3", "DQ4", "DQ5", "DQ6", "DQ7", "DQ8", "DQ9"]
)
def test_every_other_rule_propagates(policy, rule_id):
    assert policy.should_propagate(rule_id) is True


def test_an_unrecognized_rule_id_defaults_to_propagating(policy):
    assert policy.should_propagate("DQ99_NOT_A_REAL_RULE") is True
