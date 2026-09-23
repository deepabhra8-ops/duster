"""Every per-row rule check must survive being shipped to a Spark executor.

The production failure this guards: Spark pickles a UDF to send it to its
executors. cloudpickle handles an ordinary Python closure, but the deployed
engine is compiled by Cython, where a nested `def` is not a types.FunctionType
- so cloudpickle declines its function path, falls back to pickling by
qualified name, and dies. The UI showed:

    Rule error: Could not serialize object: AttributeError: Can't pickle local
    object 'DQ5RangeRule.validate.<locals>.is_valid'

and every row of that rule was recorded as not checked. Only the rules using
native Spark expressions (DQ1/DQ3/DQ6/DQ7) kept working.

Local tests could never catch it, because locally the engine is plain Python
and closures pickle fine. So these tests assert the structural property that
makes Cython irrelevant instead: the check is an instance of a module-level
class, so pickle stores the class *by reference* and never introspects a
function.
"""
from __future__ import annotations

import inspect
import pickletools
import types
from pathlib import Path

import pytest
from pyspark import cloudpickle

from engine.rules.dq2_date_format import _MatchesDateFormat
from engine.rules.dq4_decimal_precision import _WithinPrecision
from engine.rules.dq5_range import _RangeCheck
from engine.rules.dq10_uniqueness import _IsNotDuplicate


CHECKS = [
    pytest.param(_MatchesDateFormat("%Y-%m-%d"), id="DQ2"),
    pytest.param(_WithinPrecision(2), id="DQ4"),
    pytest.param(_RangeCheck("0", "100"), id="DQ5"),
    pytest.param(_IsNotDuplicate({("a",)}), id="DQ10"),
]


class TestPicklable:
    @pytest.mark.parametrize("check", CHECKS)
    def test_it_pickles(self, check):
        assert cloudpickle.loads(cloudpickle.dumps(check)) is not None

    @pytest.mark.parametrize("check", CHECKS)
    def test_its_class_is_stored_by_reference(self, check):
        """The property that makes Cython irrelevant. A by-value pickle would
        mean cloudpickle introspected the object, which is what breaks."""
        opcodes = [
            op.name for op, _, _ in pickletools.genops(cloudpickle.dumps(check))
        ]

        assert "STACK_GLOBAL" in opcodes or "GLOBAL" in opcodes

    @pytest.mark.parametrize("check", CHECKS)
    def test_it_is_not_a_plain_function(self, check):
        """A function here would be the old, Cython-fragile shape."""
        assert not isinstance(check, types.FunctionType)
        assert callable(check)

    @pytest.mark.parametrize("check", CHECKS)
    def test_it_is_defined_at_module_level(self, check):
        """A local class would pickle no better than a local function."""
        assert "<locals>" not in type(check).__qualname__


class TestBehaviourSurvivesTheRoundTrip:
    def test_range_check(self):
        restored = cloudpickle.loads(cloudpickle.dumps(_RangeCheck("0", "100")))

        assert restored(50) is True
        assert restored(150) is False
        assert restored(None) is True

    def test_date_format_check(self):
        restored = cloudpickle.loads(
            cloudpickle.dumps(_MatchesDateFormat("%Y-%m-%d"))
        )

        assert restored("2023-01-01") is True
        assert restored("01/01/2023") is False

    def test_precision_check(self):
        restored = cloudpickle.loads(cloudpickle.dumps(_WithinPrecision(2)))

        assert restored("1.55") is True
        assert restored("1.555") is False

    def test_duplicate_check(self):
        restored = cloudpickle.loads(cloudpickle.dumps(_IsNotDuplicate({("a",)})))

        assert restored("a") is False
        assert restored("b") is True
        assert restored(None) is True


class TestNoRuleReintroducesAClosure:
    def test_no_rule_defines_a_nested_check_function(self):
        """Catches the next author who reaches for the obvious `def is_valid`
        inside validate() - it works locally and fails only once deployed."""
        rules_dir = Path(inspect.getfile(_RangeCheck)).parent
        offenders = []

        for path in sorted(rules_dir.glob("dq*.py")):
            source = path.read_text(encoding="utf-8")

            for number, line in enumerate(source.splitlines(), start=1):
                stripped = line.strip()

                # A def indented past column 4 is nested inside a method.
                if stripped.startswith("def ") and line.startswith(" " * 8):
                    offenders.append(f"{path.name}:{number}: {stripped}")

        assert not offenders, (
            "These nested functions will not pickle once the engine is "
            "Cythonised; use a module-level callable class instead:\n  "
            + "\n  ".join(offenders)
        )
