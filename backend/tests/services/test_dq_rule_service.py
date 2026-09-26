from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from engine.quality.models import RuleValidationError
from repositories.dq_rule_repository import DqRuleConflictError, format_rule_id, parse_rule_id
from services import dq_rule_service as module
from services.dq_rule_service import DqRulePermissionError, DqRuleService, rule_from_record


class FakeRuleRepository:
    def __init__(self):
        self.rows: dict[int, dict] = {}
        self.next_id = 1

    def _record(self, pk, fields, username, version):
        return {
            "rule_id": format_rule_id(pk),
            "version": version,
            "created_by": username,
            "updated_by": username,
            "created_at": datetime(2026, 9, 26, 6, 10),
            "updated_at": datetime(2026, 9, 26, 6, 10),
            "last_run_id": None,
            "last_run_at": None,
            "last_run_counts": None,
            **fields,
        }

    def list_all(self):
        return sorted(self.rows.values(), key=lambda r: r["rule_name"])

    def get(self, rule_id):
        return self.rows.get(parse_rule_id(rule_id))

    def create(self, fields, username):
        if any(r["rule_name"] == fields["rule_name"] for r in self.rows.values()):
            raise DqRuleConflictError(f"A rule named '{fields['rule_name']}' already exists")

        pk, self.next_id = self.next_id, self.next_id + 1
        self.rows[pk] = self._record(pk, fields, username, 1)
        return self.rows[pk]

    def update(self, rule_id, fields, username, expected_version=None):
        row = self.get(rule_id)

        if expected_version is not None and row["version"] != expected_version:
            raise DqRuleConflictError("changed by someone else")

        row.update(fields, version=row["version"] + 1, updated_by=username)
        return row

    def delete(self, rule_id):
        return self.rows.pop(parse_rule_id(rule_id), None) is not None


class FakeRuns:
    def __init__(self, latest=None):
        self.latest = latest

    def latest_done(self, before=None):
        return self.latest


PAYLOAD = {
    "name": "amounts_in_range",
    "description": "  Order amounts stay in range. ",
    "template": "in_range",
    "params": {"min": "0", "max": "250000"},
    "threshold": {"metric": "pass_rate", "op": ">=", "value": 0.99},
    "severity": "error",
    "scope": {"level": "schema", "catalog": "main", "schema": "sales*", "column": "*_amount", "exclude": ["main.dq.*"]},
}


@pytest.fixture
def service():
    return DqRuleService(repository=FakeRuleRepository(), runs=FakeRuns())


def test_create_normalises_and_returns_the_api_shape(service):
    rule = service.create(PAYLOAD, "alice")

    assert rule["ruleId"] == "R001"
    assert rule["name"] == "amounts_in_range"
    assert rule["description"] == "Order amounts stay in range."
    assert rule["params"] == {"min": 0, "max": 250000, "boundsInclusive": True}
    assert rule["dimension"] == "validity"
    assert rule["level"] == "row"
    assert rule["scope"] == {
        "level": "schema", "catalog": "main", "schema": "sales*", "table": "*", "column": "*_amount",
        "exclude": ["main.dq.*"], "tableTypes": ["MANAGED", "EXTERNAL"],
    }
    assert rule["createdAt"] == "2026-09-26T06:10:00Z"
    assert rule["lastRun"] is None


def test_template_default_dimension_is_not_stored_as_an_override(service):
    service.create({**PAYLOAD, "dimension": "validity"}, "alice")
    assert service.repository.rows[1]["dimension"] is None

    service.create({**PAYLOAD, "name": "other", "dimension": "accuracy"}, "alice")
    assert service.repository.rows[2]["dimension"] == "accuracy"


def test_stored_records_round_trip_into_rule_instances(service):
    service.create(PAYLOAD, "alice")
    rule = rule_from_record(service.repository.rows[1])

    assert rule.rule_id == "R001"
    assert rule.scope.exclude == ("main.dq.*",)
    assert rule.threshold.value == 0.99


def test_invalid_payload_is_rejected(service):
    with pytest.raises(RuleValidationError):
        service.create({**PAYLOAD, "template": "nope"}, "alice")


def test_update_bumps_the_version_and_keeps_enabled_when_omitted(service):
    service.create(PAYLOAD, "alice")
    service.set_enabled("R001", False, "alice")

    updated = service.update("R001", {**PAYLOAD, "severity": "warn"}, "alice")

    assert updated["version"] == 3
    assert updated["severity"] == "warn"
    assert updated["enabled"] is False


def test_update_with_a_stale_version_conflicts(service):
    service.create(PAYLOAD, "alice")

    with pytest.raises(DqRuleConflictError):
        service.update("R001", {**PAYLOAD, "version": 7}, "alice")


def test_only_the_owner_or_an_admin_can_change_a_rule(service):
    service.create(PAYLOAD, "alice")

    with patch.object(module.user_repository, "is_admin", return_value=False):
        with pytest.raises(DqRulePermissionError):
            service.update("R001", PAYLOAD, "bob")
        with pytest.raises(DqRulePermissionError):
            service.delete("R001", "bob")

    with patch.object(module.user_repository, "is_admin", return_value=True):
        assert service.set_enabled("R001", False, "bob")["enabled"] is False


def test_missing_rules(service):
    assert service.get("R404") is None
    assert service.get("not-an-id") is None
    assert service.update("R404", PAYLOAD, "alice") is None
    assert service.delete("R404", "alice") is False


def test_duplicate_picks_a_free_name(service):
    service.create(PAYLOAD, "alice")

    first = service.duplicate("R001", "bob")
    second = service.duplicate("R001", "bob")

    assert first["name"] == "amounts_in_range_copy"
    assert second["name"] == "amounts_in_range_copy2"
    assert first["createdBy"] == "bob"
    assert first["description"] == "Order amounts stay in range."


def test_library_counts_failing_enabled_rules():
    repository = FakeRuleRepository()
    service = DqRuleService(
        repository=repository,
        runs=FakeRuns({"run_id": "run-1", "completed_at": datetime(2026, 9, 26, 6, 10)}),
    )
    service.create(PAYLOAD, "alice")
    service.create({**PAYLOAD, "name": "b"}, "alice")
    service.create({**PAYLOAD, "name": "c", "enabled": False}, "alice")

    for pk, counts in ((1, {"FAIL": 1, "PASS": 11}), (2, {"PASS": 3}), (3, {"ERROR": 1})):
        repository.rows[pk].update(last_run_id="run-1", last_run_at=datetime(2026, 9, 26), last_run_counts=counts)

    library = service.library()

    assert library["totalRules"] == 3
    assert library["failingRules"] == 1
    assert library["lastRun"] == {"runId": "run-1", "completedAt": "2026-09-26T06:10:00Z"}
    assert library["rules"][0]["lastRun"]["counts"] == {"FAIL": 1, "PASS": 11}


def test_templates_are_listed(service):
    assert {t["name"] for t in service.templates()} >= {"in_range", "sql_row", "row_count"}
