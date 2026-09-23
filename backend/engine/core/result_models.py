"""Dataclasses representing rule, table, dimension, validation, and profiling results produced by the engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from pyspark.sql import Column, DataFrame


# Where a rule's outcome status lives in RuleResult.metadata, and its values.
# A rule that could not be performed at all (no reference list, no configured
# columns, an unparseable expression, an internal error) must be excluded from
# scoring rather than counted as a pass - see BaseRule.create_not_run_result
# and DimensionScorer. Absent status means STATUS_OK, so older engine builds
# and stored results keep their existing meaning.
STATUS_KEY = "status"
STATUS_OK = "ok"
STATUS_NOT_RUN = "not_run"


@dataclass(frozen=True)
class RuleResult:
    """Outcome of running one rule against one column: a pass/fail predicate plus notes.

    ``pass_mask`` is an unevaluated Spark ``Column`` predicate rather than a materialized
    boolean Series - Spark has no cheap equivalent of a pandas Series decoupled from its
    DataFrame. Because of that, ``invalid_count``/``total_count`` can't be derived from the
    mask here (there's no ``data`` to filter against a bare ``Column``); the caller
    (``RuleExecutor``) fills them in via ``metadata["_total_count"]`` after running the rule.
    """

    pass_mask: Column
    invalid_count: int
    notes: str
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate invalid_count."""
        if self.invalid_count < 0:
            raise ValueError(
                "RuleResult.invalid_count cannot be negative."
            )

    @property
    def pass_count(self) -> int:
        """Number of rows that passed the rule."""
        return self.total_count - self.invalid_count

    @property
    def total_count(self) -> int:
        """Total number of rows evaluated."""
        return int(self.metadata.get("_total_count", self.invalid_count))

    @property
    def score(self) -> float:
        """Pass ratio for this rule, 1.0 when there are no rows."""
        if self.total_count == 0:
            return 1.0

        return self.pass_count / self.total_count

    @property
    def status(self) -> str:
        """STATUS_OK, or STATUS_NOT_RUN when the check could not be performed."""
        return self.metadata.get(STATUS_KEY, STATUS_OK)

    @property
    def was_run(self) -> bool:
        """Whether this rule actually judged the data, and so should be scored.

        A not-run rule's ``score`` is still 1.0 by construction (its mask is
        all-pass), which is exactly why callers must consult this before
        averaging it into anything.
        """
        return self.status != STATUS_NOT_RUN


@dataclass(frozen=True)
class RuleExecutionDetail:
    """Summary of one rule's execution against one column, for reporting."""

    table_name: str
    column_name: str
    rule_id: str
    dimension: str
    cde: bool
    rule_notes: str
    total_rows: int
    invalid_count: int
    pass_count: int
    score: float

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate row counts and score are internally consistent."""
        if self.total_rows < 0:
            raise ValueError(
                "total_rows cannot be negative."
            )

        if self.invalid_count < 0:
            raise ValueError(
                "invalid_count cannot be negative."
            )

        if self.pass_count < 0:
            raise ValueError(
                "pass_count cannot be negative."
            )

        if (
            self.invalid_count
            + self.pass_count
            != self.total_rows
        ):
            raise ValueError(
                "invalid_count + pass_count must equal "
                "total_rows."
            )

        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                "score must be between 0.0 and 1.0."
            )

    @property
    def status(self) -> str:
        """STATUS_OK, or STATUS_NOT_RUN when the check could not be performed.

        Defaults to STATUS_OK when absent so results produced by an engine build
        that predates the status key keep their original meaning.
        """
        return self.metadata.get(STATUS_KEY, STATUS_OK)

    @property
    def was_run(self) -> bool:
        """Whether this rule actually judged the data, and so should be scored."""
        return self.status != STATUS_NOT_RUN

    @classmethod
    def from_rule_result(
        cls,
        *,
        table_name: str,
        column_name: str,
        rule_id: str,
        dimension: str,
        cde: bool,
        result: RuleResult,
    ) -> "RuleExecutionDetail":
        """Build a RuleExecutionDetail from a RuleResult."""
        return cls(
            table_name=table_name,
            column_name=column_name,
            rule_id=rule_id,
            dimension=dimension,
            cde=cde,
            rule_notes=result.notes,
            total_rows=result.total_count,
            invalid_count=result.invalid_count,
            pass_count=result.pass_count,
            score=result.score,
            metadata=result.metadata,
        )


@dataclass(frozen=True)
class RowFailure:
    """One rule failure recorded against one row."""

    column_name: str
    rule_id: str
    notes: str
    failed_value: Any = None
    dimension: str = ""
    category: str = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


@dataclass
class TableValidationResult:
    """Validation outcome for one table: rule details, pass/fail rows, and row-level failures."""

    table_name: str
    total_rows: int
    pass_mask: Column

    rule_details: list[RuleExecutionDetail] = field(
        default_factory=list
    )

    passed_rows: Optional[DataFrame] = None
    failed_rows: Optional[DataFrame] = None

    row_failures: dict[Any, list[RowFailure]] = field(
        default_factory=dict
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate total_rows.

        Unlike the pandas version, ``pass_mask`` here is an unevaluated Spark ``Column``
        predicate with no length of its own, so it can't be cross-checked against
        ``total_rows`` - ``fail_count`` instead reads the already-computed
        ``metadata["failed_row_count"]`` the builder (``TableValidator``) fills in.
        """
        if self.total_rows < 0:
            raise ValueError(
                "total_rows cannot be negative."
            )

    @property
    def pass_count(self) -> int:
        """Number of rows that passed validation."""
        return self.total_rows - self.fail_count

    @property
    def fail_count(self) -> int:
        """Number of rows that failed validation."""
        return int(self.metadata.get("failed_row_count", 0))

    @property
    def score(self) -> float:
        """Pass ratio for this table, 1.0 when there are no rows."""
        if self.total_rows == 0:
            return 1.0

        return self.pass_count / self.total_rows

    def add_rule_detail(
        self,
        detail: RuleExecutionDetail,
    ) -> None:
        """Append a rule execution detail."""
        self.rule_details.append(detail)

    def add_row_failure(
        self,
        row_index: Any,
        failure: RowFailure,
    ) -> None:
        """Record a row-level failure."""
        self.row_failures.setdefault(
            row_index,
            [],
        ).append(failure)


@dataclass(frozen=True)
class DimensionResult:
    """Aggregated score for one DQ dimension across the rules that contribute to it."""

    dimension: str
    scores: Sequence[float]
    score: float

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate the aggregate and individual scores are within range."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                "Dimension score must be between 0.0 and 1.0."
            )

        for value in self.scores:
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    "Individual dimension scores must be "
                    "between 0.0 and 1.0."
                )

    @classmethod
    def from_scores(
        cls,
        dimension: str,
        scores: Sequence[float],
    ) -> "DimensionResult":
        """Build a DimensionResult by averaging the given scores."""

        if not scores:
            score = 1.0
        else:
            score = sum(scores) / len(scores)

        return cls(
            dimension=dimension,
            scores=tuple(scores),
            score=score,
        )


@dataclass(frozen=True)
class ValidationSummary:
    """Overall validation score aggregated from per-dimension results."""

    dimension_results: Mapping[str, DimensionResult]
    overall_score: float

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate the overall score is within range."""
        if not 0.0 <= self.overall_score <= 1.0:
            raise ValueError(
                "Overall score must be between 0.0 and 1.0."
            )

    @classmethod
    def from_dimensions(
        cls,
        dimension_results: Mapping[str, DimensionResult],
    ) -> "ValidationSummary":
        """Build a ValidationSummary by averaging the given dimension results."""

        if not dimension_results:
            overall_score = 1.0
        else:
            overall_score = (
                sum(
                    result.score
                    for result in dimension_results.values()
                )
                / len(dimension_results)
            )

        return cls(
            dimension_results=dict(
                dimension_results
            ),
            overall_score=overall_score,
        )

    @property
    def dimensions(self) -> list[str]:
        """Names of the dimensions included in this summary."""
        return list(
            self.dimension_results.keys()
        )


@dataclass
class ValidationRunResult:
    """Full result of one validation run: per-table results plus the run-level summary."""

    project_name: str
    run_timestamp: str
    summary: ValidationSummary

    tables: dict[
        str,
        TableValidationResult,
    ] = field(
        default_factory=dict
    )

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def overall_score(self) -> float:
        """Overall DQ score for the run."""
        return self.summary.overall_score

    @property
    def total_tables(self) -> int:
        """Number of tables included in the run."""
        return len(self.tables)

    @property
    def total_rows(self) -> int:
        """Total rows validated across all tables."""
        return sum(
            table.total_rows
            for table in self.tables.values()
        )

    @property
    def total_failed_rows(self) -> int:
        """Total failed rows across all tables."""
        return sum(
            table.fail_count
            for table in self.tables.values()
        )

    def add_table_result(
        self,
        result: TableValidationResult,
    ) -> None:
        """Add or replace a table's validation result."""
        self.tables[result.table_name] = result


@dataclass(frozen=True)
class ProfileColumnResult:
    """Profiling statistics for one column."""

    column_name: str
    dtype: str
    total_count: int
    null_count: int
    distinct_count: int
    min_value: Any = ""
    max_value: Any = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def null_percentage(self) -> float:
        """Percentage of null values in this column."""
        if self.total_count == 0:
            return 0.0

        return (
            self.null_count
            / self.total_count
        ) * 100

    @property
    def unique_percentage(self) -> float:
        """Percentage of distinct values in this column."""
        if self.total_count == 0:
            return 0.0

        return (
            self.distinct_count
            / self.total_count
        ) * 100


@dataclass(frozen=True)
class TableProfileResult:
    """Profiling result for one table: its column-level statistics."""

    table_name: str
    columns: Sequence[ProfileColumnResult]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def column_count(self) -> int:
        """Number of profiled columns."""
        return len(self.columns)


@dataclass(frozen=True)
class ProfileRunResult:
    """Full result of one profiling run across all configured tables."""

    project_name: str
    run_timestamp: str
    tables: Mapping[
        str,
        TableProfileResult,
    ]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    # Table name -> short reason, for tables that could not be profiled while
    # others in the same run could.
    failed_tables: Mapping[str, str] = field(
        default_factory=dict
    )

    @property
    def table_count(self) -> int:
        """Number of profiled tables."""
        return len(self.tables)


@dataclass(frozen=True)
class RuleConfiguration:
    """Configured DQ rules for one column."""

    column_name: str
    rule_ids: Sequence[str]
    parameters: str = ""
    cde: bool = False
    analyst_notes: str = ""

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class TableRuleConfiguration:
    """Configured DQ rules for one table, grouped by column."""

    table_name: str
    columns: Sequence[RuleConfiguration]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def column_count(self) -> int:
        """Number of configured columns."""
        return len(self.columns)


def create_empty_pass_mask() -> Column:
    """Return an all-True pass mask predicate."""
    from pyspark.sql.functions import lit

    return lit(True)


def combine_pass_masks(
    current_mask: Column,
    rule_mask: Column,
) -> Column:
    """Combine two pass mask predicates with logical AND."""
    return current_mask & rule_mask
