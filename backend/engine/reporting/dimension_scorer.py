"""Pure scoring math for dimension reports: score clamping, percentage/bar formatting, and good/warning/poor grading."""

from __future__ import annotations

from typing import Any

import polars as pl


class DimensionScorer:
    """Computes and formats dimension scores; has no knowledge of worksheets."""

    GOOD_THRESHOLD = 0.95
    WARNING_THRESHOLD = 0.80

    def safe_score(
        self,
        value: Any,
    ) -> float:
        """Coerce a value to a score clamped to [0.0, 1.0]."""

        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, score))

    def safe_integer(
        self,
        value: Any,
    ) -> int:
        """Coerce a value to an int, defaulting to 0."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def format_score(
        self,
        score: float,
        precision: int = 2,
    ) -> str:
        """Render a 0..1 score as a percentage string, e.g. '93.7%'."""

        return f"{round(score * 100, precision)}%"

    def score_bar(
        self,
        score: float,
        width: int = 10,
    ) -> str:
        """Render a 0..1 score as a filled/empty block bar."""

        score = max(0.0, min(1.0, float(score)))
        filled = int(score * width)

        return "█" * filled + "░" * (width - filled)

    def overall_score(
        self,
        dataframe: pl.DataFrame,
    ) -> float:
        """Average the 'Score' column of a dimension DataFrame."""

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
        """Grade a score as 'good', 'warning', or 'poor'."""

        if score >= self.GOOD_THRESHOLD:
            return "good"

        if score >= self.WARNING_THRESHOLD:
            return "warning"

        return "poor"
