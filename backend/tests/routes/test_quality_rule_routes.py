from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from engine.quality.models import RuleValidationError
from repositories.dq_rule_repository import DqRuleConflictError
from routes import quality_rule_routes as routes
from services.dq_rule_service import DqRulePermissionError


class _FakeRequest:
    def __init__(self, body=None, query=None, raw_error=False):
        self._body = body
        self._raw_error = raw_error
        self.query_params = query or {}

    async def json(self):
        if self._raw_error:
            raise ValueError("not json")
        return self._body


def _body(response):
    return response if isinstance(response, dict) else json.loads(response.body)


def _status(response):
    return getattr(response, "status_code", 200)


def run(coro):
    return asyncio.run(coro)


RULE = {"ruleId": "R001", "name": "amounts_in_range"}


def test_create_rule_returns_201_with_the_owner_set():
    with patch.object(routes.dq_rule_service, "create", return_value=RULE) as create:
        response = run(routes.create_rule(_FakeRequest({"name": "x"}), username="alice"))

    assert _status(response) == 201
    assert _body(response) == {"ok": True, "data": RULE}
    assert create.call_args.args == ({"name": "x"}, "alice")


def test_create_rule_maps_validation_and_conflict_errors():
    with patch.object(routes.dq_rule_service, "create", side_effect=RuleValidationError("name must start with a letter")):
        response = run(routes.create_rule(_FakeRequest({}), username="alice"))
    assert _status(response) == 400
    assert _body(response)["error"] == "name must start with a letter"

    with patch.object(routes.dq_rule_service, "create", side_effect=DqRuleConflictError("already exists")):
        assert _status(run(routes.create_rule(_FakeRequest({}), username="alice"))) == 409


def test_non_object_bodies_are_rejected():
    assert _status(run(routes.create_rule(_FakeRequest([1, 2]), username="alice"))) == 400
    assert _status(run(routes.create_rule(_FakeRequest(raw_error=True), username="alice"))) == 400


def test_update_rule_status_codes():
    with patch.object(routes.dq_rule_service, "update", return_value=None):
        assert _status(run(routes.update_rule("R404", _FakeRequest({}), username="alice"))) == 404

    with patch.object(routes.dq_rule_service, "update", side_effect=DqRulePermissionError("owner only")):
        assert _status(run(routes.update_rule("R001", _FakeRequest({}), username="bob"))) == 403

    with patch.object(routes.dq_rule_service, "update", side_effect=DqRuleConflictError("stale")):
        assert _status(run(routes.update_rule("R001", _FakeRequest({}), username="alice"))) == 409


def test_patch_toggles_enabled():
    with patch.object(routes.dq_rule_service, "set_enabled", return_value={**RULE, "enabled": False}) as set_enabled:
        response = run(routes.set_rule_enabled("R001", _FakeRequest({"enabled": False}), username="alice"))

    assert _body(response)["data"]["enabled"] is False
    assert set_enabled.call_args.args == ("R001", False, "alice")


def test_get_and_delete_rule():
    with patch.object(routes.dq_rule_service, "get", return_value=None):
        assert _status(routes.get_rule("R404")) == 404

    with patch.object(routes.dq_rule_service, "delete", return_value=True):
        assert _body(routes.delete_rule("R001", username="alice")) == {"ok": True}

    with patch.object(routes.dq_rule_service, "delete", side_effect=DqRulePermissionError("owner only")):
        assert _status(routes.delete_rule("R001", username="bob")) == 403


def test_library_failure_is_a_500_without_details():
    with patch.object(routes.dq_rule_service, "library", side_effect=RuntimeError("db password=hunter2")):
        response = routes.list_rules()

    assert _status(response) == 500
    assert "hunter2" not in json.dumps(_body(response))


def test_dry_run_passes_the_body_through():
    plan = {"tableCount": 6}

    with patch.object(routes.dq_run_service, "dry_run", return_value=plan) as dry_run:
        response = run(routes.dry_run(_FakeRequest({"rule": {"name": "x"}})))

    assert _body(response) == {"ok": True, "data": plan}
    assert dry_run.call_args.args == ({"rule": {"name": "x"}},)


def test_start_run_is_accepted_asynchronously():
    with patch.object(routes.dq_run_service, "start", return_value={"runId": "abc", "status": "queued"}):
        response = run(routes.start_run(_FakeRequest({}), username="alice"))

    assert _status(response) == 202
    assert _body(response)["data"]["status"] == "queued"


def test_run_results_paging_validation():
    assert _status(routes.get_run_results("latest", _FakeRequest(query={"page": "0"}))) == 400
    assert _status(routes.get_run_results("latest", _FakeRequest(query={"pageSize": "100000"}))) == 400
    assert _status(routes.get_run_results("latest", _FakeRequest(query={"page": "x"}))) == 400

    with patch.object(routes.dq_run_service, "results_page", return_value=None):
        assert _status(routes.get_run_results("missing", _FakeRequest())) == 404

    with patch.object(routes.dq_run_service, "results_page", return_value={"items": []}) as page:
        routes.get_run_results("latest", _FakeRequest(query={"status": "FAIL", "page": "2", "pageSize": "25"}))

    assert page.call_args.args == ("latest", "FAIL", 2, 25)


def test_get_run_404():
    with patch.object(routes.dq_run_service, "summary", return_value=None):
        assert _status(routes.get_run("missing")) == 404


def test_csv_download_sets_an_attachment_header():
    with patch.object(routes.dq_run_service, "results_csv", return_value=("abc", "run_id\nabc\n")):
        response = routes.download_run_results("latest")

    assert response.media_type.startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="dq-results-abc.csv"'


def test_cancel_run_outcomes():
    for outcome, status in (("not_found", 404), ("forbidden", 403), ("not_cancellable", 409), ("cancelling", 200)):
        with patch.object(routes.dq_run_service, "cancel", return_value=outcome):
            assert _status(routes.cancel_run("abc", username="alice")) == status
