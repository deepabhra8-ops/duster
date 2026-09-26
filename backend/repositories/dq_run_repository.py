from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import case, func

from core.db import get_db_session
from repositories.models import DqResult, DqRun
from utils.logger import get_logger


logger = get_logger(__name__)

_INSERT_CHUNK = 1000

# Worst first: what needs attention leads, skipped (not evaluated) trails.
_STATUS_ORDER = ("FAIL", "ERROR", "WARN", "NO_DATA", "PASS", "SKIPPED")

_RESULT_FIELDS = {
    "catalog": "catalog_name",
    "schema": "schema_name",
    "table": "table_name",
    "column": "column_name",
}

_RUN_FIELDS = (
    "run_id", "status", "requested_by", "rule_ids", "scope_override", "where_clause",
    "sample_fraction", "max_parallel_tables", "rule_count", "table_count", "result_count",
    "progress_current", "progress_total", "error_message", "engine_version",
    "created_at", "started_at", "completed_at", "duration_ms",
)


class DqRunRepository:
    def create(self, run_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                row = DqRun(run_id=run_id, status="queued", **fields)
                session.add(row)
                session.commit()
                return self._run_dict(row)
        except Exception:
            logger.exception("Failed to create data-quality run '%s'", run_id)
            raise

    def get(self, run_id: str) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                row = session.get(DqRun, run_id)
                return self._run_dict(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read data-quality run '%s'", run_id)
            raise

    def latest_done(self, before: Any = None) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                query = session.query(DqRun).filter(DqRun.status == "done")

                if before is not None:
                    query = query.filter(DqRun.completed_at < before)

                row = query.order_by(DqRun.completed_at.desc()).first()
                return self._run_dict(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read the latest data-quality run")
            raise

    def list_page(self, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        try:
            with get_db_session() as session:
                total = session.query(func.count(DqRun.run_id)).scalar() or 0
                rows = (
                    session.query(DqRun)
                    .order_by(DqRun.created_at.desc())
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                    .all()
                )
                return [self._run_dict(row) for row in rows], int(total)
        except Exception:
            logger.exception("Failed to list data-quality runs")
            raise

    def list_by_statuses(self, statuses: Iterable[str]) -> list[dict[str, Any]]:
        try:
            with get_db_session() as session:
                rows = session.query(DqRun).filter(DqRun.status.in_(tuple(statuses))).all()
                return [self._run_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to list data-quality runs by status")
            raise

    def update(self, run_id: str, **fields: Any) -> None:
        try:
            with get_db_session() as session:
                session.query(DqRun).filter(DqRun.run_id == run_id).update(
                    {getattr(DqRun, key): value for key, value in fields.items()},
                    synchronize_session=False,
                )
                session.commit()
        except Exception:
            logger.exception("Failed to update data-quality run '%s'", run_id)
            raise

    def transition(self, run_id: str, from_statuses: set[str], to_status: str, **fields: Any) -> bool:
        try:
            with get_db_session() as session:
                values = {DqRun.status: to_status}
                values.update({getattr(DqRun, key): value for key, value in fields.items()})

                changed = (
                    session.query(DqRun)
                    .filter(DqRun.run_id == run_id, DqRun.status.in_(tuple(from_statuses)))
                    .update(values, synchronize_session=False)
                )
                session.commit()

            if changed:
                logger.info("Data-quality run '%s' moved to '%s'", run_id, to_status)
            else:
                logger.info(
                    "Data-quality run '%s' not moved to '%s'; it is no longer in %s",
                    run_id,
                    to_status,
                    sorted(from_statuses),
                )

            return bool(changed)
        except Exception:
            logger.exception("Failed to move data-quality run '%s' to '%s'", run_id, to_status)
            raise

    def insert_results(self, run_id: str, records: list[dict[str, Any]]) -> None:
        rows = [self._result_row(run_id, record) for record in records]

        try:
            with get_db_session() as session:
                for start in range(0, len(rows), _INSERT_CHUNK):
                    session.bulk_insert_mappings(DqResult, rows[start:start + _INSERT_CHUNK])

                session.commit()

            logger.info("Stored %s result(s) for data-quality run '%s'", len(rows), run_id)
        except Exception:
            logger.exception("Failed to store results for data-quality run '%s'", run_id)
            raise

    def results(self, run_id: str) -> list[dict[str, Any]]:
        try:
            with get_db_session() as session:
                rows = session.query(DqResult).filter(DqResult.run_id == run_id).all()
                return [self._result_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to read results for data-quality run '%s'", run_id)
            raise

    def status_counts(self, run_id: str) -> dict[str, int]:
        try:
            with get_db_session() as session:
                rows = (
                    session.query(DqResult.status, func.count(DqResult.id))
                    .filter(DqResult.run_id == run_id)
                    .group_by(DqResult.status)
                    .all()
                )
                return {status: int(count) for status, count in rows}
        except Exception:
            logger.exception("Failed to count results for data-quality run '%s'", run_id)
            raise

    def results_page(
        self,
        run_id: str,
        statuses: tuple[str, ...] | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            with get_db_session() as session:
                query = session.query(DqResult).filter(DqResult.run_id == run_id)

                if statuses:
                    query = query.filter(DqResult.status.in_(statuses))

                total = query.with_entities(func.count(DqResult.id)).scalar() or 0
                status_rank = case(
                    {status: rank for rank, status in enumerate(_STATUS_ORDER)},
                    value=DqResult.status,
                    else_=len(_STATUS_ORDER),
                )
                rows = (
                    query.order_by(
                        status_rank,
                        DqResult.fail_count.desc(),
                        DqResult.catalog_name,
                        DqResult.schema_name,
                        DqResult.table_name,
                        DqResult.column_name,
                        DqResult.id,
                    )
                    .offset(max(page - 1, 0) * page_size)
                    .limit(page_size)
                    .all()
                )
                return [self._result_dict(row) for row in rows], int(total)
        except Exception:
            logger.exception("Failed to page results for data-quality run '%s'", run_id)
            raise

    @staticmethod
    def _result_row(run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        row = {"run_id": run_id}

        for key, value in record.items():
            row[_RESULT_FIELDS.get(key, key)] = value

        return row

    @staticmethod
    def _result_dict(row: DqResult) -> dict[str, Any]:
        return {
            "rule_id": row.rule_id,
            "rule_name": row.rule_name,
            "rule_version": row.rule_version,
            "template": row.template,
            "dimension": row.dimension,
            "rule_level": row.rule_level,
            "severity": row.severity,
            "weight": row.weight,
            "catalog": row.catalog_name,
            "schema": row.schema_name,
            "table": row.table_name,
            "column": row.column_name,
            "total_count": row.total_count,
            "pass_count": row.pass_count,
            "fail_count": row.fail_count,
            "metric_value": row.metric_value,
            "threshold_metric": row.threshold_metric,
            "threshold_op": row.threshold_op,
            "threshold_value": row.threshold_value,
            "status": row.status,
            "message": row.message,
            "where_clause": row.where_clause,
            "sampled": bool(row.sampled),
            "sample_fraction": row.sample_fraction,
            "duration_ms": row.duration_ms,
        }

    @staticmethod
    def _run_dict(row: DqRun) -> dict[str, Any]:
        return {field: getattr(row, field) for field in _RUN_FIELDS}


dq_run_repository = DqRunRepository()
