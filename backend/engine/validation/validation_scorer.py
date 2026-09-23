from __future__ import annotations

from typing import Mapping

from engine.core.execution_context import ExecutionContext
from engine.rules.rule_registry import RuleRegistry
from utils.logger import get_logger


logger = get_logger(__name__)


class ValidationScorer:
    def __init__(
        self,
        context: ExecutionContext,
        rule_registry: RuleRegistry,
    ) -> None:
        try:
            self.context = context
            self.rule_registry = rule_registry
            logger.debug("Initialized validation scorer")
        except Exception:
            logger.exception("Failed to initialize validation scorer")
            raise

    def calculate_rule_score(
        self,
        total_rows: int,
        invalid_count: int,
    ) -> float:
        try:
            if total_rows <= 0:
                return 1.0

            pass_count = total_rows - invalid_count
            score = pass_count / total_rows
            logger.debug("Calculated rule score: %s", score)
            return score
        except Exception:
            logger.exception("Failed to calculate rule score")
            raise

    def get_dimension(
        self,
        rule_id: str,
        context: ExecutionContext | None = None,
    ) -> str:
        execution_context = (
            context
            or self.context
        )

        try:
            rule = self.rule_registry.get(
                rule_id=rule_id,
                context=execution_context,
            )

            dimension = rule.dimension or "Other"
            logger.debug("Resolved rule '%s' to dimension '%s'", rule_id, dimension)
            return dimension

        except KeyError:
            logger.debug("Rule '%s' not found; using dimension 'Other'", rule_id)
            return "Other"
        except Exception:
            logger.exception("Failed to resolve dimension for rule '%s'", rule_id)
            raise

    def get_category(
        self,
        rule_id: str,
        context: ExecutionContext | None = None,
    ) -> str:
        execution_context = (
            context
            or self.context
        )

        try:
            rule = self.rule_registry.get(
                rule_id=rule_id,
                context=execution_context,
            )

            category = rule.category or "Other"
            logger.debug("Resolved rule '%s' to category '%s'", rule_id, category)
            return category

        except KeyError:
            logger.debug("Rule '%s' not found; using category 'Other'", rule_id)
            return "Other"
        except Exception:
            logger.exception("Failed to resolve category for rule '%s'", rule_id)
            raise

    def add_rule_score(
        self,
        dimension_scores: dict[
            str,
            list[float],
        ],
        rule_id: str,
        score: float,
    ) -> None:
        try:
            dimension = self.get_dimension(
                rule_id=rule_id,
            )

            dimension_scores.setdefault(
                dimension,
                [],
            ).append(score)
        except Exception:
            logger.exception("Failed to add score for rule '%s'", rule_id)
            raise

    def calculate_dimension_scores(
        self,
        dimension_scores: Mapping[
            str,
            list[float],
        ],
    ) -> dict[str, float]:
        try:
            result = {
                dimension: (
                    sum(values) / len(values)
                    if values
                    else 1.0
                )
                for dimension, values
                in dimension_scores.items()
            }
            logger.debug("Calculated scores for %s dimensions", len(result))
            return result
        except Exception:
            logger.exception("Failed to calculate dimension scores")
            raise

    def calculate_overall_score(
        self,
        dimension_scores: Mapping[
            str,
            float,
        ],
    ) -> float:
        try:
            if not dimension_scores:
                return 1.0

            score = (
                sum(dimension_scores.values())
                / len(dimension_scores)
            )
            logger.debug("Calculated overall score: %s", score)
            return score
        except Exception:
            logger.exception("Failed to calculate overall score")
            raise

    def calculate_scores(
        self,
        dimension_rule_scores: Mapping[
            str,
            list[float],
        ],
    ) -> tuple[
        dict[str, float],
        float,
    ]:
        try:
            dimension_scores = (
                self.calculate_dimension_scores(
                    dimension_rule_scores
                )
            )

            overall_score = (
                self.calculate_overall_score(
                    dimension_scores
                )
            )

            return dimension_scores, overall_score
        except Exception:
            logger.exception("Failed to calculate validation scores")
            raise
