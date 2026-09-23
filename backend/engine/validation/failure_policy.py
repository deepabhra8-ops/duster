from __future__ import annotations

from utils.logger import get_logger


logger = get_logger(__name__)


class FailurePolicy:
    NON_PROPAGATING_RULES = frozenset(
        {
            "DQ10",
            "DQ11",
        }
    )

    def should_propagate(
        self,
        rule_id: str,
    ) -> bool:
        try:
            result = (
                rule_id
                not in self.NON_PROPAGATING_RULES
            )
            logger.debug(
                "Failure policy for rule '%s': propagate=%s",
                rule_id,
                result,
            )
            return result
        except Exception:
            logger.exception(
                "Failed to evaluate failure policy for rule '%s'",
                rule_id,
            )
            raise
