"""Unit tests for RuleRegistry - the same registry pattern as connectors/data
sources/profilers, exercised on its own local instance (not the global default_rule_registry,
to avoid interfering with the app's real rule registrations).
"""
from __future__ import annotations

import pytest

from engine.rules.base_rule import BaseRule
from engine.rules.rule_registry import RuleRegistry


class _RuleA(BaseRule):
    rule_id = "TESTRULE_A"

    def validate(self, data, column_name, parameters, context):
        raise NotImplementedError


class _RuleB(BaseRule):
    rule_id = "testrule_b"  # lowercase - normalization should upper-case it

    def validate(self, data, column_name, parameters, context):
        raise NotImplementedError


@pytest.fixture
def registry() -> RuleRegistry:
    return RuleRegistry()


def test_register_and_get_roundtrip(registry):
    registry.register(_RuleA)
    rule = registry.get("TESTRULE_A", context=None)
    assert isinstance(rule, _RuleA)


def test_rule_id_lookup_is_case_insensitive(registry):
    registry.register(_RuleB)
    assert registry.contains("TESTRULE_B") is True
    assert registry.contains("testrule_b") is True


def test_registering_a_duplicate_rule_id_raises(registry):
    registry.register(_RuleA)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_RuleA)


def test_get_raises_key_error_for_an_unregistered_rule(registry):
    with pytest.raises(KeyError):
        registry.get("NOT_REGISTERED", context=None)


def test_a_class_without_a_rule_id_cannot_be_registered(registry):
    class _NoRuleId(BaseRule):
        def validate(self, data, column_name, parameters, context):
            raise NotImplementedError

    with pytest.raises(ValueError, match="must define a non-empty"):
        registry.register(_NoRuleId)


def test_unregister_removes_a_rule(registry):
    registry.register(_RuleA)
    registry.unregister("TESTRULE_A")
    assert registry.contains("TESTRULE_A") is False


def test_all_and_rule_ids_reflect_registered_rules(registry):
    registry.register(_RuleA)
    registry.register(_RuleB)

    assert set(registry.rule_ids()) == {"TESTRULE_A", "TESTRULE_B"}
    assert registry.all() == {"TESTRULE_A": _RuleA, "TESTRULE_B": _RuleB}


def test_clear_removes_every_registered_rule(registry):
    registry.register(_RuleA)
    registry.clear()
    assert registry.rule_ids() == []
