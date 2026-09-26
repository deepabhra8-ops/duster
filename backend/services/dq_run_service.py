from __future__ import annotations

import csv
import io
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Mapping

from core.config import (
    DQ_DEFAULT_PARALLEL_TABLES,
    DQ_DRY_RUN_MAX_TABLES,
    DQ_MAX_EXPRS_PER_PASS,
    DQ_MAX_PARALLEL_TABLES,
    DQ_RUN_WORKERS,
)
from engine.quality import rollup
from engine.quality.dry_run import dry_run
from engine.quality.evaluator import short_error
from engine.quality.executor import DQExecutor, RunOptions, with_scope
from engine.quality.models import (
    ENGINE_VERSION,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_WARN,
    STATUSES,
    RuleInstance,
    RuleValidationError,
    finite_float,
)
from engine.quality.rule_loader import parse_rule, parse_scope
from engine.quality.scope import ScopeResolver
from engine.quality.sql_text import check_sql_fragment
from engine.quality.templates import REGISTRY
from repositories.dq_rule_repository import DqRuleRepository, dq_rule_repository
from repositories.dq_run_repository import DqRunRepository, dq_run_repository
from repositories.user_repository import user_repository
from services.dq_rule_service import iso, rule_from_record
from utils.job_cancellation import JobCancelledError
from utils.logger import get_logger


logger = get_logger(__name__)

LATEST = "latest"
ACTIVE_STATUSES = ("queued", "running", "cancelling")
MAX_RULES_PER_RUN = 500

_RUN_POOL = ThreadPoolExecutor(max_workers=max(1, DQ_RUN_WORKERS), thread_name_prefix="dq-run")

_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

CSV_COLUMNS = (
    "run_id", "run_ts", "rule_id", "rule_name", "rule_version", "template", "dimension",
    "rule_level", "severity", "catalog", "schema", "table", "column", "total_count",
    "pass_count", "fail_count", "metric_value", "threshold_metric", "threshold_op",
    "threshold_value", "status", "message", "where_clause", "sampled", "sample_fraction",
    "duration_ms",
)


def _csv_safe(value: Any) -> Any:
    # A cell starting with = + - @ is run as a formula by spreadsheet apps; object
    # names and error messages come from the scanned sources, so they aren't trusted.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def parse_run_options(payload: Mapping[str, Any]) -> RunOptions:
    where = payload.get("where")

    if where is not None and not isinstance(where, str):
        raise RuleValidationError("where must be a string")

    where = check_sql_fragment(where, "where") if where and where.strip() else None

    fraction = payload.get("sampleFraction")

    if fraction in (None, ""):
        fraction = None
    else:
        fraction = finite_float(fraction, "sampleFraction")

        if not 0 < fraction <= 1:
            raise RuleValidationError("sampleFraction must be greater than 0 and at most 1")

        fraction = None if fraction == 1 else fraction

    parallel = payload.get("maxParallelTables", DQ_DEFAULT_PARALLEL_TABLES)

    if isinstance(parallel, bool) or not isinstance(parallel, int) or not 1 <= parallel <= DQ_MAX_PARALLEL_TABLES:
        raise RuleValidationError(f"maxParallelTables must be a whole number from 1 to {DQ_MAX_PARALLEL_TABLES}")

    return RunOptions(
        where=where,
        sample_fraction=fraction,
        max_parallel_tables=parallel,
        max_exprs_per_pass=DQ_MAX_EXPRS_PER_PASS,
    )


def _rule_ids(payload: Mapping[str, Any]) -> list[str] | None:
    rule_ids = payload.get("ruleIds")

    if rule_ids is None:
        return None

    if not isinstance(rule_ids, list) or not all(isinstance(rule_id, str) for rule_id in rule_ids):
        raise RuleValidationError("ruleIds must be a list of rule ids")

    rule_ids = list(dict.fromkeys(rule_id.strip() for rule_id in rule_ids if rule_id.strip()))

    if not rule_ids:
        raise RuleValidationError("ruleIds must name at least one rule")

    if len(rule_ids) > MAX_RULES_PER_RUN:
        raise RuleValidationError(f"A run takes at most {MAX_RULES_PER_RUN} rules")

    return rule_ids


def run_to_api(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runId": run["run_id"],
        "status": run["status"],
        "requestedBy": run.get("requested_by"),
        "ruleIds": run.get("rule_ids"),
        "scope": run.get("scope_override"),
        "where": run.get("where_clause"),
        "sampleFraction": run.get("sample_fraction"),
        "maxParallelTables": run.get("max_parallel_tables"),
        "ruleCount": run.get("rule_count") or 0,
        "tableCount": run.get("table_count") or 0,
        "resultCount": run.get("result_count") or 0,
        "progress": {"current": run.get("progress_current") or 0, "total": run.get("progress_total") or 0},
        "errorMessage": run.get("error_message"),
        "engineVersion": run.get("engine_version"),
        "createdAt": iso(run.get("created_at")),
        "startedAt": iso(run.get("started_at")),
        "completedAt": iso(run.get("completed_at")),
        "durationMs": run.get("duration_ms"),
    }


def result_to_api(record: Mapping[str, Any]) -> dict[str, Any]:
    parts = [record.get(key) for key in ("catalog", "schema", "table", "column")]

    return {
        "status": record["status"],
        "ruleId": record["rule_id"],
        "ruleName": record["rule_name"],
        "ruleVersion": record.get("rule_version"),
        "template": record["template"],
        "dimension": record.get("dimension"),
        "level": record.get("rule_level"),
        "severity": record.get("severity"),
        "catalog": parts[0],
        "schema": parts[1],
        "table": parts[2],
        "column": parts[3],
        "target": ".".join(part for part in parts if part),
        "totalCount": record.get("total_count"),
        "passCount": record.get("pass_count"),
        "failCount": record.get("fail_count"),
        "metricValue": record.get("metric_value"),
        "threshold": {
            "metric": record.get("threshold_metric"),
            "op": record.get("threshold_op"),
            "value": record.get("threshold_value"),
        },
        "message": record.get("message"),
        "where": record.get("where_clause"),
        "sampled": bool(record.get("sampled")),
        "sampleFraction": record.get("sample_fraction"),
        "durationMs": record.get("duration_ms"),
    }


def _statuses_for(status_filter: str) -> tuple[str, ...] | None:
    status_filter = (status_filter or rollup.ALL).strip()

    if status_filter == rollup.ALL:
        return None

    if status_filter == rollup.ATTENTION:
        return tuple(status for status in STATUSES if rollup.needs_attention(status))

    if status_filter in STATUSES:
        return (status_filter,)

    raise RuleValidationError(f"status must be one of: {rollup.ATTENTION}, {', '.join(STATUSES)}, {rollup.ALL}")


class DqRunService:
    def __init__(
        self,
        rules: DqRuleRepository | None = None,
        runs: DqRunRepository | None = None,
        catalog_factory: Callable[[], Any] | None = None,
        source_factory: Callable[[Any], Any] | None = None,
        submit: Callable[[str], None] | None = None,
    ) -> None:
        self.rules = rules or dq_rule_repository
        self.runs = runs or dq_run_repository
        self._catalog_factory = catalog_factory
        self._source_factory = source_factory
        self._submit = submit or (lambda run_id: _RUN_POOL.submit(self._execute_safely, run_id))

    # ---- wiring (lazy, so importing this module never needs Spark or a database) ----

    def _catalog(self):
        if self._catalog_factory is not None:
            return self._catalog_factory()

        from services.dq_sources import ConnectionCatalog

        return ConnectionCatalog()

    def _source(self, catalog):
        if self._source_factory is not None:
            return self._source_factory(catalog)

        from services.dq_sources import ConnectionTableSource

        return ConnectionTableSource(catalog)

    # ---- rules ----

    def _load_rules(self, rule_ids: list[str] | None) -> tuple[list[RuleInstance], list[dict[str, Any]]]:
        records = self.rules.get_many(rule_ids) if rule_ids is not None else self.rules.list_enabled()

        if rule_ids is not None:
            missing = sorted(set(rule_ids) - {record["rule_id"] for record in records})

            if missing:
                raise RuleValidationError(f"Unknown rule id(s): {', '.join(missing)}")

        rules: list[RuleInstance] = []
        broken: list[dict[str, Any]] = []

        for record in records:
            try:
                rules.append(rule_from_record(record))
            except RuleValidationError as exc:
                logger.warning("Rule %s can't be loaded: %s", record["rule_id"], exc)
                broken.append(self._broken_rule_result(record, str(exc)))

        return rules, broken

    @staticmethod
    def _broken_rule_result(record: Mapping[str, Any], message: str) -> dict[str, Any]:
        template = REGISTRY.get(record["template"])

        return {
            "rule_id": record["rule_id"],
            "rule_name": record["rule_name"],
            "rule_version": record.get("version"),
            "template": record["template"],
            "dimension": record.get("dimension") or (template.dimension if template else None),
            "rule_level": template.level if template else "row",
            "severity": record.get("severity") or "error",
            "weight": record.get("weight"),
            "status": STATUS_ERROR,
            "threshold_metric": record.get("threshold_metric") or "pass_rate",
            "threshold_op": record.get("threshold_op") or ">=",
            "threshold_value": record.get("threshold_value") or 0.0,
            "message": f"Rule definition is invalid: {message}"[:2000],
            "sampled": False,
        }

    # ---- dry run ----

    def dry_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        draft = payload.get("rule")

        if draft is not None:
            if not isinstance(draft, Mapping):
                raise RuleValidationError("rule must be an object")

            rules = [parse_rule(draft, rule_id=str(draft.get("ruleId") or "DRAFT"))]
        else:
            rules, _ = self._load_rules(_rule_ids(payload))

        if not rules:
            raise RuleValidationError("There are no enabled rules to plan")

        scope = parse_scope(payload["scope"]) if payload.get("scope") else None
        options = parse_run_options(payload)
        resolver = ScopeResolver(self._catalog())

        plan = dry_run(
            resolver,
            with_scope(rules, scope),
            where=options.where,
            sample_fraction=options.sample_fraction,
            max_exprs_per_pass=options.max_exprs_per_pass,
            max_tables=DQ_DRY_RUN_MAX_TABLES,
        )
        plan["ruleCount"] = len(rules)
        return plan

    # ---- runs ----

    def start(self, payload: Mapping[str, Any], username: str) -> dict[str, Any]:
        rule_ids = _rule_ids(payload)
        rules, broken = self._load_rules(rule_ids)

        if not rules and not broken:
            raise RuleValidationError("There are no enabled rules to run")

        scope = payload.get("scope") or None

        if scope is not None:
            parse_scope(scope)

        options = parse_run_options(payload)
        run_id = str(uuid.uuid4())

        run = self.runs.create(
            run_id,
            {
                "requested_by": username,
                "rule_ids": rule_ids,
                "scope_override": dict(scope) if scope else None,
                "where_clause": options.where,
                "sample_fraction": options.sample_fraction,
                "max_parallel_tables": options.max_parallel_tables,
                "rule_count": len(rules) + len(broken),
                "engine_version": ENGINE_VERSION,
            },
        )

        logger.info("Queued data-quality run '%s' (%s rule(s)) for '%s'", run_id, len(rules) + len(broken), username)
        self._submit(run_id)
        return run_to_api(run)

    def _execute_safely(self, run_id: str) -> None:
        try:
            self.execute(run_id)
        except Exception:
            logger.exception("Data-quality run '%s' crashed outside its own error handling", run_id)

    def execute(self, run_id: str) -> None:
        run = self.runs.get(run_id)

        if run is None or not self.runs.transition(run_id, {"queued"}, "running", started_at=datetime.utcnow()):
            logger.info("Data-quality run '%s' is no longer queued; not starting it", run_id)
            return

        cancel_event = threading.Event()

        with _cancel_lock:
            _cancel_events[run_id] = cancel_event

        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            rules, broken = self._load_rules(run.get("rule_ids"))
            scope = parse_scope(run["scope_override"]) if run.get("scope_override") else None
            options = RunOptions(
                where=run.get("where_clause"),
                sample_fraction=run.get("sample_fraction"),
                max_parallel_tables=run.get("max_parallel_tables") or DQ_DEFAULT_PARALLEL_TABLES,
                max_exprs_per_pass=DQ_MAX_EXPRS_PER_PASS,
            )

            catalog = self._catalog()
            executor = DQExecutor(
                self._source(catalog),
                ScopeResolver(catalog),
                options,
                cancel_event=cancel_event,
                progress=lambda done, total: self.runs.update(run_id, progress_current=done, progress_total=total),
            )

            self._set_job_group(run_id)
            outcome = executor.run(with_scope(rules, scope))
            records = broken + [record.to_dict() for record in outcome.results]

            self.runs.insert_results(run_id, records)
            completed = datetime.utcnow()

            moved = self.runs.transition(
                run_id,
                {"running", "cancelling"},
                "done",
                completed_at=completed,
                duration_ms=elapsed(),
                table_count=len(outcome.tables),
                result_count=len(records),
            )

            if moved:
                self.rules.record_last_run(run_id, completed, rollup.rule_status_counts(records))
                self._notify(run, records, len(outcome.tables))

        except JobCancelledError:
            logger.info("Data-quality run '%s' cancelled", run_id)
            self.runs.transition(
                run_id,
                {"running", "cancelling"},
                "cancelled",
                completed_at=datetime.utcnow(),
                duration_ms=elapsed(),
            )

        except Exception as exc:
            logger.exception("Data-quality run '%s' failed", run_id)
            self.runs.transition(
                run_id,
                {"running", "cancelling"},
                "error",
                completed_at=datetime.utcnow(),
                duration_ms=elapsed(),
                error_message=short_error(exc),
            )
            self._notify_failure(run, short_error(exc))

        finally:
            with _cancel_lock:
                _cancel_events.pop(run_id, None)

    @staticmethod
    def _set_job_group(run_id: str) -> None:
        try:
            from engine.core.spark_session import get_spark_session

            get_spark_session().sparkContext.setJobGroup(run_id, f"DQ run {run_id}", interruptOnCancel=True)
        except Exception:
            logger.warning("Could not set the Spark job group for run '%s'", run_id, exc_info=True)

    def cancel(self, run_id: str, username: str) -> str:
        run = self.runs.get(run_id)

        if run is None:
            return "not_found"

        if run.get("requested_by") != username and not user_repository.is_admin(username):
            return "forbidden"

        if self.runs.transition(run_id, {"queued"}, "cancelled", completed_at=datetime.utcnow()):
            return "cancelled"

        if not self.runs.transition(run_id, {"running"}, "cancelling"):
            return "not_cancellable"

        with _cancel_lock:
            event = _cancel_events.get(run_id)

        if event is not None:
            event.set()

        try:
            from engine.core.spark_session import get_spark_session

            get_spark_session().sparkContext.cancelJobGroup(run_id)
        except Exception:
            logger.warning("Could not cancel the Spark job group for run '%s'", run_id, exc_info=True)

        return "cancelling"

    def reset_interrupted(self) -> int:
        settled = 0

        for run in self.runs.list_by_statuses(ACTIVE_STATUSES):
            if self.runs.transition(
                run["run_id"],
                set(ACTIVE_STATUSES),
                "error",
                completed_at=datetime.utcnow(),
                error_message="Interrupted by a server restart. Start the run again.",
            ):
                settled += 1

        if settled:
            logger.warning("Marked %s data-quality run(s) as failed after a restart interrupted them", settled)

        return settled

    # ---- reading ----

    def _resolve(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.latest_done() if run_id == LATEST else self.runs.get(run_id)

    def list_runs(self, page: int, page_size: int) -> dict[str, Any]:
        rows, total = self.runs.list_page(page, page_size)
        return {
            "items": [run_to_api(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size if page_size else 1,
        }

    def summary(self, run_id: str) -> dict[str, Any] | None:
        run = self._resolve(run_id)

        if run is None:
            return None

        payload: dict[str, Any] = {"run": run_to_api(run)}

        if run["status"] != "done":
            return payload

        payload.update(rollup.summarize(self.runs.results(run["run_id"])))

        previous = self.runs.latest_done(before=run.get("completed_at"))
        payload["previous"] = (
            {
                "runId": previous["run_id"],
                "completedAt": iso(previous.get("completed_at")),
                "kpis": rollup.kpis(self.runs.results(previous["run_id"])),
            }
            if previous
            else None
        )
        return payload

    def results_page(self, run_id: str, status: str, page: int, page_size: int) -> dict[str, Any] | None:
        statuses = _statuses_for(status)
        run = self._resolve(run_id)

        if run is None:
            return None

        rows, total = self.runs.results_page(run["run_id"], statuses, page, page_size)
        counts = dict.fromkeys(STATUSES, 0)
        counts.update(self.runs.status_counts(run["run_id"]))
        counts[rollup.ATTENTION] = sum(counts[s] for s in STATUSES if rollup.needs_attention(s))
        counts[rollup.ALL] = sum(counts[s] for s in STATUSES)

        return {
            "runId": run["run_id"],
            "items": [result_to_api(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size if page_size else 1,
            "counts": counts,
        }

    def results_csv(self, run_id: str) -> tuple[str, str] | None:
        run = self._resolve(run_id)

        if run is None:
            return None

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        run_ts = iso(run.get("completed_at")) or ""

        for record in self.runs.results(run["run_id"]):
            row = {**record, "run_id": run["run_id"], "run_ts": run_ts}
            writer.writerow([_csv_safe(row.get(column)) for column in CSV_COLUMNS])

        return run["run_id"], buffer.getvalue()

    # ---- notifications ----

    def _notify(self, run: Mapping[str, Any], records: list[dict[str, Any]], table_count: int) -> None:
        failing = sum(1 for record in records if record["status"] == STATUS_FAIL)
        warnings = sum(1 for record in records if record["status"] == STATUS_WARN)
        errors = sum(1 for record in records if record["status"] == STATUS_ERROR)

        self._send(
            run,
            "Quality run finished" if not (failing or errors) else f"Quality run finished: {failing} failing",
            f"{failing} failing · {warnings} warnings · {errors} errors across {table_count} table(s)",
        )

    def _notify_failure(self, run: Mapping[str, Any], message: str) -> None:
        self._send(run, "Quality run failed", message)

    @staticmethod
    def _send(run: Mapping[str, Any], title: str, content: str) -> None:
        username = run.get("requested_by")

        if not username:
            return

        try:
            from services.notification_service import notification_service

            notification_service.create(
                username,
                type="dq_run",
                title=title,
                content=content[:1000],
                link="/quality-rules/runs",
                username=username,
            )
        except Exception:
            logger.warning("Could not notify '%s' about run '%s'", username, run.get("run_id"), exc_info=True)


dq_run_service = DqRunService()
