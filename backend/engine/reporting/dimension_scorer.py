from __future__ import annotations

from typing import Any

import polars as pl


class DimensionScorer:
    GOOD_THRESHOLD = 0.95
    WARNING_THRESHOLD = 0.80

    def safe_score(
        self,
        value: Any,
    ) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, score))

    def safe_integer(
        self,
        value: Any,
    ) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def format_score(
        self,
        score: float,
        precision: int = 2,
    ) -> str:
        return f"{round(score * 100, precision)}%"

    def score_bar(
        self,
        score: float,
        width: int = 10,
    ) -> str:
        score = max(0.0, min(1.0, float(score)))
        filled = int(score * width)

        return "█" * filled + "░" * (width - filled)

    def overall_score(
        self,
        dataframe: pl.DataFrame,
    ) -> float:
        if dataframe.is_empty() or "Score" not in dataframe.columns:
            return 1.0

        scores = [
            self.safe_score(value)
            for value in dataframe["Score"]
        ]

        if not scores:
            return 1.0

        return sum(scores) / len(scores)

    def bucket(
        self,
        score: float,
    ) -> str:
        if score >= self.GOOD_THRESHOLD:
            return "good"

        if score >= self.WARNING_THRESHOLD:
            return "warning"

        return "poor"
