from __future__ import annotations

import dataclasses
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from engine.core.parallel import run_in_parallel
from engine.quality.evaluator import (
    error_record,
    evaluate_counts,
    evaluate_value,
    record_for,
    short_error,
    skip_record,
)
from engine.quality.models import (
    LEVEL_CROSS_TABLE,
    LEVEL_ROW,
    STATUS_ERROR,
    ResultRecord,
    RuleInstance,
    Scope,
    TableRef,
)
from engine.quality.planner import (
    ROWS_ALIAS,
    AggExpr,
    PreparedBinding,
    ScanPass,
    filter_sql,
    plan_bindings,
    plan_passes,
    prepare,
)
from engine.quality.scope import ScopeResolver
from engine.quality.templates import BindingError, full_value_pattern, get_template, parse_parent_table
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)


class TableScan(Protocol):
    def columns(self) -> list[tuple[str, str]]: ...

    def restrict(self, where: str) -> "TableScan": ...

    def check_boolean(self, sql: str) -> None: ...

    def check_regex(self, pattern: str) -> None: ...

    def aggregate(self, exprs: list[AggExpr], sample: tuple[float, int] | None = None) -> dict[str, Any]: ...

    def key_coverage(
        self,
        column: str,
        row_filter: str | None,
        parent: "TableScan",
        parent_column: str,
    ) -> tuple[int, int]: ...


class TableSource(Protocol):
    def open(self, table: TableRef) -> TableScan: ...


@dataclass(frozen=True)
class RunOptions:
    where: str | None = None
    sample_fraction: float | None = None
    sample_seed: int = 42
    max_parallel_tables: int = 4
    max_exprs_per_pass: int = 400


@dataclass
class RunOutcome:
    results: list[ResultRecord] = field(default_factory=list)
    tables: list[TableRef] = field(default_factory=list)


def with_scope(rules: list[RuleInstance], scope: Scope | None) -> list[RuleInstance]:
    """A run-level scope replaces each rule's default scope, so one rule library can be
    pointed anywhere ("run all gold rules on this new schema")."""
    if scope is None:
        return list(rules)

    return [dataclasses.replace(rule, scope=scope) for rule in rules]


class DQExecutor:
    def __init__(
        self,
        source: TableSource,
        resolver: ScopeResolver,
        options: RunOptions | None = None,
        *,
        cancel_event: threading.Event | None = None,
        progress: Callable[[int, int], None] | None = None,
        parallel: Callable[..., list] = run_in_parallel,
    ) -> None:
        self.source = source
        self.resolver = resolver
        self.options = options or RunOptions()
        self.cancel_event = cancel_event
        self.progress = progress
        self.parallel = parallel

        self._regex_errors: dict[str, str | None] = {}
        self._regex_lock = threading.Lock()
        self._done = 0
        self._done_lock = threading.Lock()

    # ---- planning ----

    def plan(self, rules: list[RuleInstance]) -> tuple[dict[TableRef, list[RuleInstance]], list[ResultRecord]]:
        plan: dict[TableRef, list[RuleInstance]] = {}
        errors: list[ResultRecord] = []

        for rule in rules:
            template = get_template(rule.template)
            resolution = self.resolver.resolve(rule.scope)

            for table in resolution.tables:
                plan.setdefault(table, []).append(rule)

            for catalog, schema, message in resolution.errors:
                errors.append(
                    record_for(rule, template, STATUS_ERROR, catalog=catalog, schema=schema, message=message)
                )

        return plan, errors

    # ---- execution ----

    def run(self, rules: list[RuleInstance]) -> RunOutcome:
        plan, results = self.plan(rules)
        tables = sorted(plan, key=lambda table: table.fqn.lower())
        self._report(0, len(tables))

        outcomes = self.parallel(
            tables,
            lambda table: self._run_and_count(table, plan[table], len(tables)),
            max_workers=self.options.max_parallel_tables,
            cancel_event=self.cancel_event,
            description="dq-table",
        )

        for outcome in outcomes:
            if outcome.ok:
                results.extend(outcome.value)
            elif isinstance(outcome.error, JobCancelledError):
                raise outcome.error
            else:
                logger.warning("DQ checks failed for %s: %s", outcome.item.fqn, outcome.error)
                results.extend(self._table_errors(outcome.item, plan[outcome.item], outcome.error))

        self._check_cancel()
        return RunOutcome(results=results, tables=tables)

    def _run_and_count(self, table: TableRef, rules: list[RuleInstance], total: int) -> list[ResultRecord]:
        try:
            return self.run_table(table, rules)
        finally:
            with self._done_lock:
                self._done += 1
                done = self._done

            self._report(done, total)

    def run_table(self, table: TableRef, rules: list[RuleInstance]) -> list[ResultRecord]:
        started = time.monotonic()
        location = {"catalog": table.catalog, "schema": table.schema, "table": table.table}
        provenance = {"where_clause": self.options.where}

        scan = self.source.open(table)

        if self.options.where:
            try:
                scan = scan.restrict(self.options.where)
            except Exception as exc:
                raise BindingError(f"Run predicate doesn't apply to this table: {short_error(exc)}") from exc

        bindings, skips = plan_bindings(table, scan.columns(), rules)
        prepared = [prepare(index, binding) for index, binding in enumerate(bindings)]

        for member in prepared:
            if member.error is None:
                member.error = self._precheck(scan, member)

        results = [skip_record(skip, location, **provenance) for skip in skips]
        results += [error_record(m.binding, location, m.error, **provenance) for m in prepared if m.error]

        sampling = self.options.sample_fraction is not None

        for scan_pass in plan_passes(prepared, self.options.max_exprs_per_pass, sampling):
            self._check_cancel()
            results += self._run_pass(scan, scan_pass, location, provenance)

        for member in prepared:
            if member.error is None and member.binding.template.level == LEVEL_CROSS_TABLE:
                self._check_cancel()
                results.append(self._run_referential(table, scan, member, location, provenance))

        elapsed = int((time.monotonic() - started) * 1000)

        for record in results:
            record.duration_ms = elapsed

        return results

    def _run_pass(
        self,
        scan: TableScan,
        scan_pass: ScanPass,
        location: dict[str, Any],
        provenance: dict[str, Any],
    ) -> list[ResultRecord]:
        sample = (self.options.sample_fraction, self.options.sample_seed) if scan_pass.sampled else None
        fields = {
            **provenance,
            "sampled": scan_pass.sampled,
            "sample_fraction": self.options.sample_fraction if scan_pass.sampled else None,
        }

        try:
            row = scan.aggregate(scan_pass.exprs, sample)
        except JobCancelledError:
            raise
        except Exception as exc:
            self._check_cancel()
            message = short_error(exc)
            return [error_record(m.binding, location, message, **fields) for m in scan_pass.members]

        rows = int(row.get(ROWS_ALIAS) or 0)
        results = []

        for member in scan_pass.members:
            index = member.index

            if member.binding.template.level == LEVEL_ROW:
                total = row.get(f"t{index}", rows)
                results.append(evaluate_counts(member.binding, location, row.get(f"p{index}"), total, **fields))
            else:
                results.append(evaluate_value(member.binding, location, row.get(f"v{index}"), rows, **fields))

        return results

    def _run_referential(
        self,
        table: TableRef,
        scan: TableScan,
        member: PreparedBinding,
        location: dict[str, Any],
        provenance: dict[str, Any],
    ) -> ResultRecord:
        binding = member.binding
        params = binding.rule.params
        fields = dict(provenance)

        try:
            catalog, schema, parent_table = parse_parent_table(params["parentTable"])
            parent_ref = TableRef(catalog or table.catalog, schema, parent_table)
            parent = self.source.open(parent_ref)
            total, found = scan.key_coverage(binding.column, binding.rule.row_filter, parent, params["parentColumn"])
        except JobCancelledError:
            raise
        except Exception as exc:
            self._check_cancel()
            return error_record(binding, location, short_error(exc), **fields)

        if found < total:
            fields["message"] = f"{total - found:,} key(s) missing from {parent_ref.fqn}"

        return evaluate_counts(binding, location, found, total, **fields)

    def _precheck(self, scan: TableScan, member: PreparedBinding) -> str | None:
        """Analyse user-authored SQL and regexes against this table before the shared
        scan, so one bad expression costs only its own binding, not the whole pass."""
        rule, template = member.binding.rule, member.binding.template

        try:
            if rule.row_filter:
                scan.check_boolean(filter_sql(rule))

            if template.name == "sql_row" and member.predicate:
                scan.check_boolean(member.predicate)

            if template.name == "regex_match":
                self._check_regex(scan, full_value_pattern(rule.params))
        except BindingError as exc:
            return str(exc)

        return None

    def _check_regex(self, scan: TableScan, pattern: str) -> None:
        with self._regex_lock:
            known = pattern in self._regex_errors
            error = self._regex_errors.get(pattern)

        if not known:
            try:
                scan.check_regex(pattern)
                error = None
            except BindingError as exc:
                error = str(exc)

            with self._regex_lock:
                self._regex_errors[pattern] = error

        if error:
            raise BindingError(error)

    def _table_errors(
        self,
        table: TableRef,
        rules: list[RuleInstance],
        error: BaseException,
    ) -> list[ResultRecord]:
        message = short_error(error)

        return [
            record_for(
                rule,
                get_template(rule.template),
                STATUS_ERROR,
                catalog=table.catalog,
                schema=table.schema,
                table=table.table,
                message=message,
                where_clause=self.options.where,
            )
            for rule in rules
        ]

    def _check_cancel(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise JobCancelledError("Run cancelled by user")

    def _report(self, done: int, total: int) -> None:
        if self.progress is None:
            return

        try:
            self.progress(done, total)
        except Exception:
            logger.warning("Could not record DQ run progress", exc_info=True)
