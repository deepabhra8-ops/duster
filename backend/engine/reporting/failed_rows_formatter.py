from __future__ import annotations

from engine.core.result_models import RowFailure


DQ_RULE_REFERENCE_COLUMN = "DQ Rule Reference"
ROW_INDEX_COLUMN = "Row Index"


class FailedRowsFormatter:
    def reference_string(
        self,
        failures: list[RowFailure],
    ) -> str:
        return "\n".join(
            f"{failure.rule_id} - {failure.dimension} - "
            f"{failure.category} - {failure.column_name}"
            for failure in failures
        )

    def sort_failures(
        self,
        failures: list[RowFailure],
    ) -> list[RowFailure]:
        return sorted(
            failures,
            key=lambda failure: (
                self._rule_sort_key(failure.rule_id),
                failure.column_name,
            ),
        )

    @staticmethod
    def _rule_sort_key(
        rule_id: str,
    ) -> tuple[int, str]:
        digits = "".join(
            character
            for character in rule_id
            if character.isdigit()
        )

        if digits:
            return (int(digits), rule_id)

        return (10**9, rule_id)
