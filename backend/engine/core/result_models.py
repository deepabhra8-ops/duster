from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from pyspark.sql import Column, DataFrame


STATUS_KEY = "status"
STATUS_OK = "ok"
STATUS_NOT_RUN = "not_run"


@dataclass(frozen=True)
class RuleResult:
    pass_mask: Column
    invalid_count: int
    notes: str
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.invalid_count < 0:
            raise ValueError(
                "RuleResult.invalid_count cannot be negative."
            )

    @property
    def pass_count(self) -> int:
        return self.total_count - self.invalid_count

    @property
    def total_count(self) -> int:
        return int(self.metadata.get("_total_count", self.invalid_count))

    @property
    def score(self) -> float:
        if self.total_count == 0:
            return 1.0

        return self.pass_count / self.total_count

    @property
    def status(self) -> str:
        return self.metadata.get(STATUS_KEY, STATUS_OK)

    @property
    def was_run(self) -> bool:
        return self.status != STATUS_NOT_RUN


@dataclass(frozen=True)
class RuleExecutionDetail:
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
        return self.metadata.get(STATUS_KEY, STATUS_OK)

    @property
    def was_run(self) -> bool:
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
        if self.total_rows < 0:
            raise ValueError(
                "total_rows cannot be negative."
            )

    @property
    def pass_count(self) -> int:
        return self.total_rows - self.fail_count

    @property
    def fail_count(self) -> int:
        return int(self.metadata.get("failed_row_count", 0))

    @property
    def score(self) -> float:
        if self.total_rows == 0:
            return 1.0

        return self.pass_count / self.total_rows

    def add_rule_detail(
        self,
        detail: RuleExecutionDetail,
    ) -> None:
        self.rule_details.append(detail)

    def add_row_failure(
        self,
        row_index: Any,
        failure: RowFailure,
    ) -> None:
        self.row_failures.setdefault(
            row_index,
            [],
        ).append(failure)


@dataclass(frozen=True)
class DimensionResult:
    dimension: str
    scores: Sequence[float]
    score: float

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
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
    dimension_results: Mapping[str, DimensionResult]
    overall_score: float

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not 0.0 <= self.overall_score <= 1.0:
            raise ValueError(
                "Overall score must be between 0.0 and 1.0."
            )

    @classmethod
    def from_dimensions(
        cls,
        dimension_results: Mapping[str, DimensionResult],
    ) -> "ValidationSummary":
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
        return list(
            self.dimension_results.keys()
        )


@dataclass
class ValidationRunResult:
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
        return self.summary.overall_score

    @property
    def total_tables(self) -> int:
        return len(self.tables)

    @property
    def total_rows(self) -> int:
        return sum(
            table.total_rows
            for table in self.tables.values()
        )

    @property
    def total_failed_rows(self) -> int:
        return sum(
            table.fail_count
            for table in self.tables.values()
        )

    def add_table_result(
        self,
        result: TableValidationResult,
    ) -> None:
        self.tables[result.table_name] = result


@dataclass(frozen=True)
class ProfileColumnResult:
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
        if self.total_count == 0:
            return 0.0

        return (
            self.null_count
            / self.total_count
        ) * 100

    @property
    def unique_percentage(self) -> float:
        if self.total_count == 0:
            return 0.0

        return (
            self.distinct_count
            / self.total_count
        ) * 100


@dataclass(frozen=True)
class TableProfileResult:
    table_name: str
    columns: Sequence[ProfileColumnResult]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def column_count(self) -> int:
        return len(self.columns)


@dataclass(frozen=True)
class ProfileRunResult:
    project_name: str
    run_timestamp: str
    tables: Mapping[
        str,
        TableProfileResult,
    ]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    failed_tables: Mapping[str, str] = field(
        default_factory=dict
    )

    @property
    def table_count(self) -> int:
        return len(self.tables)


@dataclass(frozen=True)
class RuleConfiguration:
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
    table_name: str
    columns: Sequence[RuleConfiguration]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def column_count(self) -> int:
        return len(self.columns)


def create_empty_pass_mask() -> Column:
    from pyspark.sql.functions import lit

    return lit(True)


def combine_pass_masks(
    current_mask: Column,
    rule_mask: Column,
) -> Column:
    return current_mask & rule_mask
