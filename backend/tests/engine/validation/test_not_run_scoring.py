from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.core.result_models import STATUS_NOT_RUN, RuleResult
from engine.validation.table_validator import TableValidator, _PendingRule


class _FakeMask:
    def __invert__(self):
        return self

    def __or__(self, other):
        return self


def _result(invalid_count: int, total: int, status: str | None = None) -> RuleResult:
    metadata: dict = {"_total_count": total}

    if status is not None:
        metadata["status"] = status

    return RuleResult(
        pass_mask=_FakeMask(),
        invalid_count=invalid_count,
        notes="",
        metadata=metadata,
    )


class TestRuleResultStatus:
    def test_absent_status_means_it_ran(self):
        assert _result(0, 100).was_run is True
        assert _result(0, 100).status == "ok"

    def test_not_run_is_reported(self):
        result = _result(0, 100, STATUS_NOT_RUN)

        assert result.was_run is False
        assert result.status == STATUS_NOT_RUN

    def test_a_not_run_result_still_scores_one_by_construction(self):
        assert _result(0, 100, STATUS_NOT_RUN).score == 1.0


class TestRecordScore:
    @pytest.fixture
    def validator(self):
        validator = TableValidator.__new__(TableValidator)
        validator.validation_scorer = MagicMock()
        validator.validation_scorer.calculate_rule_score.side_effect = (
            lambda total_rows, invalid_count: (
                1.0 if total_rows == 0 else (total_rows - invalid_count) / total_rows
            )
        )
        return validator

    def test_a_rule_that_ran_is_scored(self, validator):
        scores: dict[str, list[float]] = {}

        validator._record_score(
            invalid_count=50,
            total_rows=100,
            dimension="Conformity",
            dimension_scores=scores,
        )

        assert scores == {"Conformity": [0.5]}

class TestFinalizeRuleScoringGate:
    @pytest.fixture
    def validator(self):
        validator = TableValidator.__new__(TableValidator)
        validator.validation_scorer = MagicMock()
        validator.validation_scorer.calculate_rule_score.side_effect = (
            lambda total_rows, invalid_count: (
                1.0 if total_rows == 0 else (total_rows - invalid_count) / total_rows
            )
        )
        validator._resolve_dimension = MagicMock(return_value="Conformity")
        validator._resolve_category = MagicMock(return_value="Other")
        validator._build_rule_detail = MagicMock(return_value=object())
        validator.failure_policy = MagicMock()
        validator.failure_policy.should_propagate.return_value = True
        return validator

    def _fold(self, validator, result, scores, rule_id="DQ8"):
        entry = _PendingRule(
            column_configuration=object(),
            column_name="claim_id",
            rule_id=rule_id,
            result=result,
        )

        validator._finalize_rule(
            table_name="claim",
            entry=entry,
            result=result,
            total_rows=100,
            fail_mask=_FakeMask(),
            rule_details=[],
            dimension_scores=scores,
        )

    def test_a_rule_that_ran_is_scored(self, validator):
        scores: dict[str, list[float]] = {}

        self._fold(validator, _result(50, 100), scores)

        assert scores == {"Conformity": [0.5]}

    def test_a_not_run_rule_is_not_scored_at_all(self, validator):
        scores: dict[str, list[float]] = {}

        self._fold(validator, _result(0, 100, STATUS_NOT_RUN), scores)

        assert scores == {}

    def test_one_real_score_plus_one_not_run_averages_to_the_real_one(self, validator):
        scores: dict[str, list[float]] = {}

        self._fold(validator, _result(50, 100), scores, rule_id="DQ1")
        self._fold(validator, _result(0, 100, STATUS_NOT_RUN), scores, rule_id="DQ8")

        recorded = scores["Conformity"]

        assert recorded == [0.5]
        assert sum(recorded) / len(recorded) == 0.5
