from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import true
from sqlalchemy.exc import IntegrityError

from core.db import get_db_session
from repositories.models import DqRule
from utils.logger import get_logger


logger = get_logger(__name__)

_RULE_ID = re.compile(r"^R(\d{1,9})$")

EDITABLE_FIELDS = (
    "rule_name",
    "description",
    "template",
    "dimension",
    "params",
    "applies_to",
    "null_policy",
    "row_filter",
    "threshold_metric",
    "threshold_op",
    "threshold_value",
    "severity",
    "weight",
    "scope_level",
    "scope_catalog",
    "scope_schema",
    "scope_table",
    "scope_column",
    "scope_exclude",
    "scope_table_types",
    "enabled",
)


class DqRuleConflictError(Exception):
    pass


def _is_duplicate_key(exc: IntegrityError) -> bool:
    # SQL Server 2601/2627: unique index / constraint violation. Other integrity
    # errors (CHECK constraints) are bugs, not conflicts, and must not be disguised.
    message = str(exc.orig)
    return "(2601)" in message or "(2627)" in message


def format_rule_id(pk: int) -> str:
    return f"R{pk:03d}"


def parse_rule_id(rule_id: str) -> int | None:
    match = _RULE_ID.match(str(rule_id or "").strip())
    return int(match.group(1)) if match else None


class DqRuleRepository:
    def list_all(self) -> list[dict[str, Any]]:
        try:
            with get_db_session() as session:
                rows = session.query(DqRule).order_by(DqRule.rule_name).all()
                return [self._to_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to list data-quality rules")
            raise

    def get(self, rule_id: str) -> dict[str, Any] | None:
        pk = parse_rule_id(rule_id)

        if pk is None:
            return None

        try:
            with get_db_session() as session:
                row = session.get(DqRule, pk)
                return self._to_dict(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read data-quality rule '%s'", rule_id)
            raise

    def get_many(self, rule_ids: Iterable[str]) -> list[dict[str, Any]]:
        pks = [pk for pk in (parse_rule_id(rule_id) for rule_id in rule_ids) if pk is not None]

        if not pks:
            return []

        try:
            with get_db_session() as session:
                rows = session.query(DqRule).filter(DqRule.id.in_(pks)).order_by(DqRule.id).all()
                return [self._to_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to read data-quality rules %s", pks)
            raise

    def list_enabled(self) -> list[dict[str, Any]]:
        try:
            with get_db_session() as session:
                # `enabled = 1`: SQL Server has no boolean type, so `IS TRUE` isn't valid T-SQL.
                rows = session.query(DqRule).filter(DqRule.enabled == true()).order_by(DqRule.id).all()
                return [self._to_dict(row) for row in rows]
        except Exception:
            logger.exception("Failed to list enabled data-quality rules")
            raise

    def create(self, fields: dict[str, Any], username: str) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                row = DqRule(created_by=username, updated_by=username, version=1)
                self._apply(row, fields)
                session.add(row)
                session.commit()

                logger.info("Created data-quality rule '%s' (%s)", row.rule_name, format_rule_id(row.id))
                return self._to_dict(row)
        except IntegrityError as exc:
            if _is_duplicate_key(exc):
                raise DqRuleConflictError(f"A rule named '{fields.get('rule_name')}' already exists") from exc

            logger.exception("Failed to create data-quality rule '%s'", fields.get("rule_name"))
            raise
        except Exception:
            logger.exception("Failed to create data-quality rule '%s'", fields.get("rule_name"))
            raise

    def update(
        self,
        rule_id: str,
        fields: dict[str, Any],
        username: str,
        expected_version: int | None = None,
    ) -> dict[str, Any] | None:
        pk = parse_rule_id(rule_id)

        if pk is None:
            return None

        try:
            with get_db_session() as session:
                row = session.get(DqRule, pk)

                if row is None:
                    return None

                if expected_version is not None and row.version != expected_version:
                    raise DqRuleConflictError(
                        f"{rule_id} was changed by someone else (now v{row.version}); reload it and try again"
                    )

                self._apply(row, fields)
                row.version = (row.version or 0) + 1
                row.updated_by = username
                row.updated_at = datetime.utcnow()
                session.commit()

                logger.info("Updated data-quality rule %s to v%s", rule_id, row.version)
                return self._to_dict(row)
        except IntegrityError as exc:
            if _is_duplicate_key(exc):
                raise DqRuleConflictError(f"A rule named '{fields.get('rule_name')}' already exists") from exc

            logger.exception("Failed to update data-quality rule '%s'", rule_id)
            raise
        except DqRuleConflictError:
            raise
        except Exception:
            logger.exception("Failed to update data-quality rule '%s'", rule_id)
            raise

    def delete(self, rule_id: str) -> bool:
        pk = parse_rule_id(rule_id)

        if pk is None:
            return False

        try:
            with get_db_session() as session:
                deleted = session.query(DqRule).filter(DqRule.id == pk).delete(synchronize_session=False)
                session.commit()
                return bool(deleted)
        except Exception:
            logger.exception("Failed to delete data-quality rule '%s'", rule_id)
            raise

    def record_last_run(
        self,
        run_id: str,
        completed_at: datetime,
        counts_by_rule: dict[str, dict[str, int]],
    ) -> None:
        pks = {parse_rule_id(rule_id): counts for rule_id, counts in counts_by_rule.items()}
        pks.pop(None, None)

        if not pks:
            return

        try:
            with get_db_session() as session:
                for row in session.query(DqRule).filter(DqRule.id.in_(list(pks))).all():
                    row.last_run_id = run_id
                    row.last_run_at = completed_at
                    row.last_run_counts = pks[row.id]

                session.commit()
        except Exception:
            logger.exception("Failed to record last-run results for run '%s'", run_id)
            raise

    @staticmethod
    def _apply(row: DqRule, fields: dict[str, Any]) -> None:
        for key in EDITABLE_FIELDS:
            if key in fields:
                setattr(row, key, fields[key])

    @staticmethod
    def _to_dict(row: DqRule) -> dict[str, Any]:
        return {
            "rule_id": format_rule_id(row.id),
            "rule_name": row.rule_name,
            "description": row.description,
            "template": row.template,
            "dimension": row.dimension,
            "params": row.params or {},
            "applies_to": row.applies_to,
            "null_policy": row.null_policy,
            "row_filter": row.row_filter,
            "threshold_metric": row.threshold_metric,
            "threshold_op": row.threshold_op,
            "threshold_value": row.threshold_value,
            "severity": row.severity,
            "weight": row.weight,
            "scope_level": row.scope_level,
            "scope_catalog": row.scope_catalog,
            "scope_schema": row.scope_schema,
            "scope_table": row.scope_table,
            "scope_column": row.scope_column,
            "scope_exclude": row.scope_exclude or [],
            "scope_table_types": row.scope_table_types or [],
            "enabled": bool(row.enabled),
            "version": row.version,
            "last_run_id": row.last_run_id,
            "last_run_at": row.last_run_at,
            "last_run_counts": row.last_run_counts,
            "created_by": row.created_by,
            "updated_by": row.updated_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


dq_rule_repository = DqRuleRepository()
