"""Decides whether a rule's failures propagate to a table's failed-row mask (DQ10/DQ11 do not; every other rule does)."""

from __future__ import annotations

from utils.logger import get_logger


logger = get_logger(__name__)


class FailurePolicy:
    """Determines whether a rule's failures should count a row as failed."""

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
        """Return whether a rule's failures should propagate to the table's failed-row mask."""
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
