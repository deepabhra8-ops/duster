from __future__ import annotations

from typing import Any, Callable

from engine.core.parallel import TaskOutcome
from engine.quality.models import TableRef
from engine.quality.templates import BindingError


class FakeCatalog:
    """CatalogProvider over a nested dict:
    {catalog: {schema: {table: [(column, family), ...]}}}. Tables whose name starts
    with "v_" are reported as views."""

    def __init__(self, tree: dict, failing: dict | None = None) -> None:
        self.tree = tree
        self.failing = failing or {}
        self.calls: list[tuple] = []

    def _maybe_fail(self, key: tuple) -> None:
        if key in self.failing:
            raise RuntimeError(self.failing[key])

    def list_catalogs(self):
        self.calls.append(("catalogs",))
        return list(self.tree)

    def list_schemas(self, catalog):
        self.calls.append(("schemas", catalog))
        self._maybe_fail((catalog,))
        return list(self.tree[catalog])

    def list_tables(self, catalog, schema):
        self.calls.append(("tables", catalog, schema))
        self._maybe_fail((catalog, schema))
        return [(name, "VIEW" if name.startswith("v_") else "TABLE") for name in self.tree[catalog][schema]]

    def list_columns(self, catalog, schema, table):
        self.calls.append(("columns", catalog, schema, table))
        self._maybe_fail((catalog, schema, table))
        return list(self.tree[catalog][schema][table])


class FakeScan:
    """TableScan whose aggregate answers come from a callback, so executor tests can
    check orchestration without a JVM."""

    def __init__(
        self,
        columns: list[tuple[str, str]],
        answer: Callable[[str], Any] | None = None,
        rows: int = 100,
        bad_sql: tuple[str, ...] = (),
        fail_aggregate: str | None = None,
        coverage: tuple[int, int] = (10, 10),
    ) -> None:
        self._columns = columns
        self.answer = answer or (lambda sql: rows)
        self.rows = rows
        self.bad_sql = bad_sql
        self.fail_aggregate = fail_aggregate
        self.coverage = coverage
        self.aggregates: list[tuple[list, Any]] = []
        self.restricted: list[str] = []

    def columns(self):
        return list(self._columns)

    def restrict(self, where):
        if "missing_col" in where:
            raise RuntimeError("[UNRESOLVED_COLUMN] missing_col cannot be resolved.\n'Filter ...")

        self.restricted.append(where)
        return self

    def check_boolean(self, sql):
        for bad in self.bad_sql:
            if bad in sql:
                raise BindingError(f"cannot resolve {bad}")

    def check_regex(self, pattern):
        if "[" in pattern and "]" not in pattern:
            raise BindingError("Invalid regular expression: Unclosed character class")

    def aggregate(self, exprs, sample=None):
        self.aggregates.append((exprs, sample))

        if self.fail_aggregate and any(self.fail_aggregate in e.sql for e in exprs):
            raise RuntimeError("An error occurred while calling o99.agg.\n: org.apache.spark.SparkException: boom\n\tat x")

        values = {"__rows": self.rows}

        for expr in exprs[1:]:
            values[expr.alias] = self.answer(expr.sql)

        return values

    def key_coverage(self, column, row_filter, parent, parent_column):
        return self.coverage


class FakeSource:
    def __init__(self, scans: dict[str, FakeScan], broken: dict[str, str] | None = None) -> None:
        self.scans = scans
        self.broken = broken or {}
        self.opened: list[str] = []

    def open(self, table: TableRef):
        self.opened.append(table.fqn)

        if table.fqn in self.broken:
            raise RuntimeError(self.broken[table.fqn])

        return self.scans[table.fqn]


def sequential(items, worker, *, max_workers, cancel_event=None, description=""):
    outcomes = []

    for index, item in enumerate(items):
        try:
            outcomes.append(TaskOutcome(index=index, item=item, value=worker(item)))
        except BaseException as exc:  # noqa: BLE001 - mirrors run_in_parallel
            outcomes.append(TaskOutcome(index=index, item=item, error=exc))

    return outcomes
