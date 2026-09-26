from __future__ import annotations

import csv
import io
from datetime import datetime
from unittest.mock import patch

import pytest

from engine.quality.models import RuleValidationError
from services import dq_run_service as module
from services.dq_run_service import DqRunService, parse_run_options

from tests.engine.quality.fakes import FakeCatalog, FakeScan, FakeSource


RULE_RECORD = {
    "rule_id": "R001",
    "rule_name": "order_id_present",
    "description": None,
    "template": "not_null",
    "dimension": None,
    "params": {},
    "applies_to": None,
    "null_policy": "ignore",
    "row_filter": None,
    "threshold_metric": "pass_rate",
    "threshold_op": ">=",
    "threshold_value": 1.0,
    "severity": "error",
    "weight": 1.0,
    "scope_level": "table",
    "scope_catalog": "main",
    "scope_schema": "sales",
    "scope_table": "orders",
    "scope_column": "order_id",
    "scope_exclude": [],
    "scope_table_types": ["MANAGED", "EXTERNAL"],
    "enabled": True,
    "version": 2,
}

TREE = {"main": {"sales": {"orders": [("order_id", "numeric")]}}}


class FakeRules:
    def __init__(self, records):
        self.records = {r["rule_id"]: r for r in records}
        self.last_run = None

    def get_many(self, rule_ids):
        return [self.records[i] for i in rule_ids if i in self.records]

    def list_enabled(self):
        return [r for r in self.records.values() if r["enabled"]]

    def record_last_run(self, run_id, completed_at, counts):
        self.last_run = (run_id, counts)


class FakeRuns:
    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.stored: dict[str, list] = {}

    def create(self, run_id, fields):
        self.runs[run_id] = {
            "run_id": run_id, "status": "queued", "created_at": datetime(2026, 9, 26, 6, 0),
            "started_at": None, "completed_at": None, "result_count": 0, "table_count": 0, **fields,
        }
        return dict(self.runs[run_id])

    def get(self, run_id):
        run = self.runs.get(run_id)
        return dict(run) if run else None

    def update(self, run_id, **fields):
        self.runs[run_id].update(fields)

    def transition(self, run_id, from_statuses, to_status, **fields):
        run = self.runs.get(run_id)

        if run is None or run["status"] not in from_statuses:
            return False

        run.update(fields, status=to_status)
        return True

    def insert_results(self, run_id, records):
        self.stored.setdefault(run_id, []).extend(records)

    def results_page(self, run_id, statuses, page, page_size):
        rows = [r for r in self.stored.get(run_id, []) if not statuses or r["status"] in statuses]
        return rows[(page - 1) * page_size: page * page_size], len(rows)

    def status_counts(self, run_id):
        counts = {}
        for r in self.stored.get(run_id, []):
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        return counts

    def results(self, run_id):
        return list(self.stored.get(run_id, []))

    def latest_done(self, before=None):
        done = [r for r in self.runs.values() if r["status"] == "done" and (before is None or r["completed_at"] < before)]
        return dict(max(done, key=lambda r: r["completed_at"])) if done else None

    def list_by_statuses(self, statuses):
        return [dict(r) for r in self.runs.values() if r["status"] in statuses]

    def list_page(self, page, page_size):
        rows = sorted(self.runs.values(), key=lambda r: r["created_at"], reverse=True)
        return [dict(r) for r in rows], len(rows)


def make_service(scan=None, records=(RULE_RECORD,), broken=None):
    submitted = []
    scan = scan or FakeScan([("order_id", "numeric")], answer=lambda sql: 98, rows=100)
    service = DqRunService(
        rules=FakeRules(list(records)),
        runs=FakeRuns(),
        catalog_factory=lambda: FakeCatalog(TREE),
        source_factory=lambda catalog: FakeSource({"main.sales.orders": scan}, broken=broken),
        submit=submitted.append,
    )
    return service, submitted


@pytest.fixture(autouse=True)
def quiet_side_effects():
    with patch.object(DqRunService, "_set_job_group"), patch.object(DqRunService, "_send") as send:
        yield send


def test_start_queues_a_run_and_execute_completes_it(quiet_side_effects):
    service, submitted = make_service()

    run = service.start({"maxParallelTables": 2}, "alice")

    assert run["status"] == "queued"
    assert run["ruleCount"] == 1
    assert submitted == [run["runId"]]

    service.execute(run["runId"])
    stored = service.runs.runs[run["runId"]]

    assert stored["status"] == "done"
    assert stored["table_count"] == 1
    assert stored["result_count"] == 1
    assert service.runs.stored[run["runId"]][0]["status"] == "FAIL"
    assert service.rules.last_run == (run["runId"], {"R001": {"FAIL": 1}})
    quiet_side_effects.assert_called_once()
    assert "1 failing" in quiet_side_effects.call_args.args[1]


def test_start_refuses_unknown_rules_and_empty_libraries():
    service, _ = make_service()

    with pytest.raises(RuleValidationError, match="Unknown rule id"):
        service.start({"ruleIds": ["R999"]}, "alice")

    empty, _ = make_service(records=())
    with pytest.raises(RuleValidationError, match="no enabled rules"):
        empty.start({}, "alice")


def test_a_run_whose_rule_no_longer_parses_records_an_error_result():
    service, _ = make_service(records=({**RULE_RECORD, "template": "retired_template"},))
    run = service.start({}, "alice")
    service.execute(run["runId"])

    [record] = service.runs.stored[run["runId"]]
    assert record["status"] == "ERROR"
    assert record["message"].startswith("Rule definition is invalid: Unknown template")


def test_scope_override_is_validated_and_applied():
    service, _ = make_service()

    with pytest.raises(RuleValidationError):
        service.start({"scope": {"tableTypes": []}}, "alice")

    run = service.start({"scope": {"catalog": "main", "schema": "nowhere"}}, "alice")
    service.execute(run["runId"])

    assert service.runs.runs[run["runId"]]["table_count"] == 0
    assert service.runs.stored[run["runId"]] == []


def test_execute_marks_crashes_as_errors():
    def unreachable_metastore():
        raise RuntimeError("metastore down")

    service, _ = make_service()
    service._catalog_factory = unreachable_metastore
    run = service.start({}, "alice")

    service.execute(run["runId"])

    stored = service.runs.runs[run["runId"]]
    assert stored["status"] == "error"
    assert stored["error_message"] == "metastore down"


def test_cancel_a_queued_run_and_permissions():
    service, _ = make_service()
    run = service.start({}, "alice")

    with patch.object(module.user_repository, "is_admin", return_value=False):
        assert service.cancel(run["runId"], "bob") == "forbidden"

    assert service.cancel(run["runId"], "alice") == "cancelled"
    assert service.cancel(run["runId"], "alice") == "not_cancellable"
    assert service.cancel("missing", "alice") == "not_found"

    service.execute(run["runId"])
    assert service.runs.runs[run["runId"]]["status"] == "cancelled"


def test_reset_interrupted_runs():
    service, _ = make_service()
    run = service.start({}, "alice")

    assert service.reset_interrupted() == 1
    assert service.runs.runs[run["runId"]]["status"] == "error"


def _finished(service, completed_at):
    run = service.start({}, "alice")
    service.execute(run["runId"])
    service.runs.runs[run["runId"]]["completed_at"] = completed_at
    return run["runId"]


def test_summary_of_latest_includes_rollups_and_previous_kpis():
    service, _ = make_service()
    first = _finished(service, datetime(2026, 9, 25, 6, 10))
    second = _finished(service, datetime(2026, 9, 26, 6, 10))

    summary = service.summary("latest")

    assert summary["run"]["runId"] == second
    assert summary["kpis"]["rowWeighted"] == pytest.approx(0.98)
    assert summary["statusCounts"]["FAIL"] == 1
    assert summary["tree"][0]["name"] == "main"
    assert summary["previous"]["runId"] == first
    assert summary["previous"]["kpis"]["rowWeighted"] == pytest.approx(0.98)


def test_summary_of_an_unfinished_run_has_no_scores():
    service, _ = make_service()
    run = service.start({}, "alice")

    summary = service.summary(run["runId"])

    assert summary["run"]["status"] == "queued"
    assert "kpis" not in summary
    assert service.summary("missing") is None


def test_results_page_filters_and_counts():
    service, _ = make_service()
    run_id = _finished(service, datetime(2026, 9, 26))

    page = service.results_page(run_id, "attention", 1, 50)

    assert page["total"] == 1
    assert page["items"][0]["target"] == "main.sales.orders.order_id"
    assert page["items"][0]["threshold"] == {"metric": "pass_rate", "op": ">=", "value": 1.0}
    assert page["counts"]["attention"] == 1 and page["counts"]["ALL"] == 1

    assert service.results_page(run_id, "PASS", 1, 50)["total"] == 0

    with pytest.raises(RuleValidationError):
        service.results_page(run_id, "BOGUS", 1, 50)


def test_results_csv_neutralises_formula_cells():
    service, _ = make_service(broken={"main.sales.orders": "=HYPERLINK(\"http://evil\")"})
    run_id = _finished(service, datetime(2026, 9, 26))

    resolved, content = service.results_csv(run_id)
    rows = list(csv.DictReader(io.StringIO(content)))

    assert resolved == run_id
    assert rows[0]["status"] == "ERROR"
    assert rows[0]["message"].startswith("'=HYPERLINK")
    assert rows[0]["run_id"] == run_id


def test_dry_run_of_a_draft_rule():
    service, _ = make_service()

    plan = service.dry_run({"rule": {
        "name": "draft", "template": "not_null",
        "scope": {"catalog": "main", "schema": "sales", "table": "orders", "column": "*"},
    }})

    assert plan["ruleCount"] == 1
    assert plan["tableCount"] == 1
    assert plan["bindingCount"] == 1
    assert "count_if(coalesce((`order_id` IS NOT NULL), false)) AS p0" in plan["scan"]["sql"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"sampleFraction": 0}, "sampleFraction"),
        ({"sampleFraction": 1.5}, "sampleFraction"),
        ({"maxParallelTables": 0}, "maxParallelTables"),
        ({"maxParallelTables": "4"}, "maxParallelTables"),
        ({"where": "a = 1; drop table x"}, "single expression"),
    ],
)
def test_run_options_validation(payload, message):
    with pytest.raises(RuleValidationError, match=message):
        parse_run_options(payload)


def test_run_options_normalise_a_full_sample_to_no_sampling():
    options = parse_run_options({"sampleFraction": "1", "where": " event_date = current_date() "})

    assert options.sample_fraction is None
    assert options.where == "event_date = current_date()"
