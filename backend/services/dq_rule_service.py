from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from engine.quality.models import STATUS_ERROR, STATUS_FAIL, RuleInstance, RuleValidationError
from engine.quality.rule_loader import MAX_DESCRIPTION_LENGTH, parse_rule
from engine.quality.templates import REGISTRY, describe_templates
from repositories.dq_rule_repository import DqRuleRepository, dq_rule_repository
from repositories.dq_run_repository import DqRunRepository, dq_run_repository
from repositories.user_repository import user_repository
from utils.logger import get_logger


logger = get_logger(__name__)


class DqRulePermissionError(Exception):
    pass


def iso(value: datetime | None) -> str | None:
    # Stored timestamps are naive UTC; say so explicitly on the wire.
    return value.isoformat() + "Z" if value is not None else None


def record_to_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": record["rule_name"],
        "description": record.get("description"),
        "template": record["template"],
        "dimension": record.get("dimension"),
        "params": record.get("params") or {},
        "appliesTo": record.get("applies_to"),
        "nullPolicy": record.get("null_policy") or "ignore",
        "rowFilter": record.get("row_filter"),
        "threshold": {
            "metric": record["threshold_metric"],
            "op": record["threshold_op"],
            "value": record["threshold_value"],
        },
        "severity": record["severity"],
        "weight": record.get("weight", 1.0),
        "scope": {
            "level": record.get("scope_level"),
            "catalog": record.get("scope_catalog"),
            "schema": record.get("scope_schema"),
            "table": record.get("scope_table"),
            "column": record.get("scope_column"),
            "exclude": record.get("scope_exclude") or [],
            "tableTypes": record.get("scope_table_types") or None,
        },
        "enabled": bool(record.get("enabled", True)),
    }


def rule_from_record(record: Mapping[str, Any]) -> RuleInstance:
    return parse_rule(record_to_payload(record), rule_id=record["rule_id"], version=record.get("version") or 1)


def _clean_description(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if len(text) > MAX_DESCRIPTION_LENGTH:
        raise RuleValidationError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    return text or None


def rule_to_fields(rule: RuleInstance, description: str | None) -> dict[str, Any]:
    template = REGISTRY[rule.template]

    return {
        "rule_name": rule.rule_name,
        "description": description,
        "template": rule.template,
        # Only an actual override is stored, so a rule keeps following its template's
        # dimension unless someone deliberately re-files it.
        "dimension": rule.dimension if rule.dimension and rule.dimension != template.dimension else None,
        "params": dict(rule.params),
        "applies_to": sorted(rule.applies_to) if rule.applies_to else None,
        "null_policy": rule.null_policy,
        "row_filter": rule.row_filter,
        "threshold_metric": rule.threshold.metric,
        "threshold_op": rule.threshold.op,
        "threshold_value": rule.threshold.value,
        "severity": rule.severity,
        "weight": rule.weight,
        "scope_level": rule.scope.level,
        "scope_catalog": rule.scope.catalog,
        "scope_schema": rule.scope.schema,
        "scope_table": rule.scope.table,
        "scope_column": rule.scope.column,
        "scope_exclude": list(rule.scope.exclude),
        "scope_table_types": list(rule.scope.table_types),
        "enabled": rule.enabled,
    }


def rule_to_api(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = record_to_payload(record)
    template = REGISTRY.get(record["template"])
    counts = record.get("last_run_counts")

    payload["scope"]["tableTypes"] = record.get("scope_table_types") or []

    return {
        "ruleId": record["rule_id"],
        **payload,
        "dimension": record.get("dimension") or (template.dimension if template else None),
        "level": template.level if template else None,
        "version": record.get("version"),
        "createdBy": record.get("created_by"),
        "updatedBy": record.get("updated_by"),
        "createdAt": iso(record.get("created_at")),
        "updatedAt": iso(record.get("updated_at")),
        "lastRun": (
            {"runId": record.get("last_run_id"), "at": iso(record.get("last_run_at")), "counts": counts or {}}
            if record.get("last_run_id")
            else None
        ),
    }


def is_failing(rule: Mapping[str, Any]) -> bool:
    counts = (rule.get("lastRun") or {}).get("counts") or {}
    return bool(rule.get("enabled")) and bool(counts.get(STATUS_FAIL) or counts.get(STATUS_ERROR))


class DqRuleService:
    def __init__(
        self,
        repository: DqRuleRepository | None = None,
        runs: DqRunRepository | None = None,
    ) -> None:
        self.repository = repository or dq_rule_repository
        self.runs = runs or dq_run_repository

    def templates(self) -> list[dict[str, Any]]:
        return describe_templates()

    def library(self) -> dict[str, Any]:
        rules = [rule_to_api(record) for record in self.repository.list_all()]
        latest = self.runs.latest_done()

        return {
            "rules": rules,
            "totalRules": len(rules),
            "failingRules": sum(1 for rule in rules if is_failing(rule)),
            "lastRun": (
                {"runId": latest["run_id"], "completedAt": iso(latest.get("completed_at"))}
                if latest
                else None
            ),
        }

    def get(self, rule_id: str) -> dict[str, Any] | None:
        record = self.repository.get(rule_id)
        return rule_to_api(record) if record is not None else None

    def create(self, payload: Mapping[str, Any], username: str) -> dict[str, Any]:
        rule = parse_rule(payload)
        fields = rule_to_fields(rule, _clean_description(payload.get("description")))
        return rule_to_api(self.repository.create(fields, username))

    def update(self, rule_id: str, payload: Mapping[str, Any], username: str) -> dict[str, Any] | None:
        existing = self.repository.get(rule_id)

        if existing is None:
            return None

        self._require_owner(existing, username, "edit")

        payload = {"enabled": existing["enabled"], **payload}
        rule = parse_rule(payload, rule_id=rule_id)
        fields = rule_to_fields(rule, _clean_description(payload.get("description")))
        expected = payload.get("version")

        if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int)):
            raise RuleValidationError("version must be an integer")

        return self._saved(self.repository.update(rule_id, fields, username, expected_version=expected))

    def set_enabled(self, rule_id: str, enabled: Any, username: str) -> dict[str, Any] | None:
        if not isinstance(enabled, bool):
            raise RuleValidationError("enabled must be true or false")

        existing = self.repository.get(rule_id)

        if existing is None:
            return None

        self._require_owner(existing, username, "enable or disable")
        return self._saved(self.repository.update(rule_id, {"enabled": enabled}, username))

    def duplicate(self, rule_id: str, username: str) -> dict[str, Any] | None:
        existing = self.repository.get(rule_id)

        if existing is None:
            return None

        taken = {record["rule_name"].lower() for record in self.repository.list_all()}
        base = f"{existing['rule_name'][:120]}_copy"
        name, suffix = base, 2

        while name.lower() in taken:
            name, suffix = f"{base}{suffix}", suffix + 1

        payload = {**record_to_payload(existing), "name": name}
        rule = parse_rule(payload)
        fields = rule_to_fields(rule, existing.get("description"))
        return rule_to_api(self.repository.create(fields, username))

    def delete(self, rule_id: str, username: str) -> bool:
        existing = self.repository.get(rule_id)

        if existing is None:
            return False

        self._require_owner(existing, username, "delete")
        return self.repository.delete(rule_id)

    @staticmethod
    def _saved(record: dict[str, Any] | None) -> dict[str, Any] | None:
        return rule_to_api(record) if record is not None else None

    @staticmethod
    def _require_owner(record: Mapping[str, Any], username: str, action: str) -> None:
        owner = record.get("created_by")

        if owner and owner == username:
            return

        if user_repository.is_admin(username):
            logger.info("Admin '%s' allowed to %s rule %s owned by '%s'", username, action, record["rule_id"], owner)
            return

        raise DqRulePermissionError(f"Only the rule's owner or an administrator can {action} it")


dq_rule_service = DqRuleService()
