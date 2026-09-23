"""Unit tests for the V2 job routes: draft lifecycle, profile-map read/edit/export.

The 409 conflict contract gets particular attention: the UI keeps the user's pending
edits and rebases them on the body of that response, so a conflict must carry both
the server's current rows and its current version.

Services are patched throughout; no database is touched.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from repositories.profile_map_repository import ProfileMapVersionConflict
from routes import job_routes


class _FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _body(response):
    return response if isinstance(response, dict) else json.loads(response.body)


def _status(response):
    return getattr(response, "status_code", 200)


JOB = {"job_id": "j1", "name": "Nightly profile", "status": "done", "step": "1"}
ROWS = [{"Table": "claim", "Column": "claim_id", "CDE (X=Yes)": ""}]


# ── draft creation ───────────────────────────────────────────────────


def test_create_draft_does_no_catalog_work():
    """Creating a draft is a single insert - catalog levels are read on demand."""
    with patch.object(
        job_routes.saved_connection_service, "get", return_value={"db_type": "postgresql"}
    ), patch.object(
        job_routes.job_service, "create_draft_job", return_value="j1"
    ) as create:
        response = asyncio.run(
            job_routes.create_draft(
                _FakeRequest({"name": "n", "connection_id": "c1", "step": "1"}),
                username="alice",
            )
        )

    body = _body(response)
    assert body["ok"] is True
    assert body["status"] == "draft"
    assert create.call_args.kwargs["connection_id"] == "c1"


def test_create_draft_rejects_unknown_connection():
    with patch.object(job_routes.saved_connection_service, "get", return_value=None):
        response = asyncio.run(
            job_routes.create_draft(
                _FakeRequest({"connection_id": "gone"}), username="alice"
            )
        )

    assert _status(response) == 400
    assert "not found" in _body(response)["error"].lower()


def test_create_draft_without_connection():
    """A flat-file draft has no connection at all."""
    with patch.object(
        job_routes.job_service, "create_draft_job", return_value="j1"
    ) as create:
        response = asyncio.run(
            job_routes.create_draft(
                _FakeRequest({"source_type": "flat_file"}), username="alice"
            )
        )

    assert _body(response)["ok"] is True
    assert create.call_args.kwargs["connection_id"] is None


# ── validator draft ──────────────────────────────────────────────────


def test_validator_draft_requires_source_job_id():
    response = asyncio.run(
        job_routes.create_validator_draft(_FakeRequest({}), username="alice")
    )

    assert _status(response) == 400


def test_validator_draft_maps_reasons_to_status_codes():
    cases = {
        "source_not_found": 404,
        "not_profile_mapper": 400,
        "source_not_done": 400,
        "no_profile_map": 400,
    }

    for reason, expected in cases.items():
        with patch.object(
            job_routes.job_service,
            "create_validator_draft",
            return_value=(None, reason),
        ):
            response = asyncio.run(
                job_routes.create_validator_draft(
                    _FakeRequest({"source_job_id": "src"}), username="alice"
                )
            )

        assert _status(response) == expected, reason


def test_validator_draft_success():
    with patch.object(
        job_routes.job_service, "create_validator_draft", return_value=("j2", "ok")
    ):
        response = asyncio.run(
            job_routes.create_validator_draft(
                _FakeRequest({"source_job_id": "src", "name": "v"}), username="alice"
            )
        )

    body = _body(response)
    assert body["job_id"] == "j2"
    assert body["status"] == "draft"


# ── draft mutation and start ─────────────────────────────────────────


def test_tables_must_be_a_list():
    response = asyncio.run(
        job_routes.update_job_tables(
            "j1", _FakeRequest({"tables": "claim"}), username="alice"
        )
    )

    assert _status(response) == 400


def test_tables_with_a_duplicate_name_are_rejected():
    """Results are keyed by table name, so a second 'customers' would silently
    overwrite the first one's profile."""
    tables = [
        {"name": "customers", "file": "a_customers.csv"},
        {"name": "Customers", "file": "b_customers.csv"},
    ]

    with patch.object(job_routes.job_service, "update_tables") as update:
        response = asyncio.run(
            job_routes.update_job_tables(
                "j1", _FakeRequest({"tables": tables}), username="alice"
            )
        )

    assert _status(response) == 400
    assert "Customers" in _body(response)["error"]
    update.assert_not_called()


def test_tables_with_distinct_names_are_accepted():
    tables = [
        {"name": "customers", "file": "a_customers.csv"},
        {"name": "orders", "file": "b_orders.csv"},
    ]

    with patch.object(job_routes.job_service, "update_tables", return_value="ok"):
        response = asyncio.run(
            job_routes.update_job_tables(
                "j1", _FakeRequest({"tables": tables}), username="alice"
            )
        )

    assert _body(response)["ok"] is True


def test_create_draft_rejects_duplicate_table_names():
    tables = [{"name": "claim"}, {"name": "claim"}]

    with patch.object(job_routes.job_service, "create_draft_job") as create:
        response = asyncio.run(
            job_routes.create_draft(
                _FakeRequest({"source_type": "flat_file", "tables": tables}),
                username="alice",
            )
        )

    assert _status(response) == 400
    create.assert_not_called()


def test_tables_rejected_once_job_is_no_longer_a_draft():
    with patch.object(job_routes.job_service, "update_tables", return_value="not_draft"):
        response = asyncio.run(
            job_routes.update_job_tables(
                "j1", _FakeRequest({"tables": []}), username="alice"
            )
        )

    assert _status(response) == 400


def test_start_requires_at_least_one_table():
    with patch.object(
        job_routes.job_service, "start_draft_job", return_value="no_tables"
    ):
        response = job_routes.start_job("j1", username="alice")

    assert _status(response) == 400
    assert "at least one table" in _body(response)["error"]


def test_start_returns_queued():
    with patch.object(job_routes.job_service, "start_draft_job", return_value="ok"):
        response = job_routes.start_job("j1", username="alice")

    assert _body(response)["status"] == "queued"


def test_delete_running_job_is_409():
    with patch.object(job_routes.job_service, "delete_job", return_value="active"):
        response = job_routes.delete_job("j1", username="alice")

    assert _status(response) == 409


# ── profile map read ─────────────────────────────────────────────────


def test_get_profile_map_returns_rows_and_version():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB), patch.object(
        job_routes.profile_map_service,
        "get_results",
        return_value={"rows": ROWS, "version": 3},
    ):
        response = job_routes.get_profile_map("j1", username="alice")

    body = _body(response)
    assert body["rows"] == ROWS
    assert body["version"] == 3
    assert body["job_name"] == "Nightly profile"
    assert body["failed_tables"] == []


def test_get_profile_map_returns_the_tables_the_run_skipped():
    skipped = [{"table": "orders", "error": "Path does not exist"}]

    with patch.object(job_routes.job_service, "get_job", return_value=JOB), patch.object(
        job_routes.profile_map_service,
        "get_results",
        return_value={"rows": ROWS, "version": 1, "failed_tables": skipped},
    ):
        response = job_routes.get_profile_map("j1", username="alice")

    assert _body(response)["failed_tables"] == skipped


def test_get_profile_map_404s_before_results_exist():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB), patch.object(
        job_routes.profile_map_service, "get_results", return_value=None
    ):
        response = job_routes.get_profile_map("j1", username="alice")

    assert _status(response) == 404


def test_get_profile_map_404s_for_another_users_job():
    with patch.object(job_routes.job_service, "get_job", return_value={}):
        response = job_routes.get_profile_map("j1", username="mallory")

    assert _status(response) == 404


# ── profile map edit ─────────────────────────────────────────────────


def _patch_edit(**kwargs):
    return patch.object(job_routes.profile_map_service, "apply_edits", **kwargs)


def test_edit_requires_integer_version():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB):
        response = asyncio.run(
            job_routes.update_profile_map(
                "j1", _FakeRequest({"version": "1", "edits": []}), username="alice"
            )
        )

    assert _status(response) == 400


def test_edit_requires_list_of_edits():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB):
        response = asyncio.run(
            job_routes.update_profile_map(
                "j1", _FakeRequest({"version": 1, "edits": {}}), username="alice"
            )
        )

    assert _status(response) == 400


def test_edit_success_returns_new_version():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB), _patch_edit(
        return_value={"rows": ROWS, "version": 4}
    ):
        response = asyncio.run(
            job_routes.update_profile_map(
                "j1", _FakeRequest({"version": 3, "edits": []}), username="alice"
            )
        )

    body = _body(response)
    assert body["ok"] is True
    assert body["version"] == 4


def test_edit_conflict_returns_409_with_server_rows_and_version():
    """The UI rebases the user's pending edits on this body, so both must be present."""
    server_rows = [{"Table": "claim", "Column": "claim_id", "CDE (X=Yes)": "X"}]

    with patch.object(job_routes.job_service, "get_job", return_value=JOB), _patch_edit(
        side_effect=ProfileMapVersionConflict(9, server_rows)
    ):
        response = asyncio.run(
            job_routes.update_profile_map(
                "j1", _FakeRequest({"version": 3, "edits": []}), username="alice"
            )
        )

    assert _status(response) == 409
    body = _body(response)
    assert body["version"] == 9
    assert body["rows"] == server_rows
    assert body["error"]


def test_edit_validation_error_is_400():
    with patch.object(job_routes.job_service, "get_job", return_value=JOB), _patch_edit(
        side_effect=ValueError("Unknown rule id: DQ99")
    ):
        response = asyncio.run(
            job_routes.update_profile_map(
                "j1", _FakeRequest({"version": 1, "edits": []}), username="alice"
            )
        )

    assert _status(response) == 400
    assert "DQ99" in _body(response)["error"]


# ── export ───────────────────────────────────────────────────────────


def test_export_returns_filename():
    with patch.object(
        job_routes.job_service,
        "export_profile_map",
        return_value=("Source_DQ_Profile_Map_j1.xlsx", "ok"),
    ):
        response = job_routes.export_profile_map("j1", username="alice")

    assert _body(response)["filename"].endswith(".xlsx")


def test_export_404s_without_results():
    with patch.object(
        job_routes.job_service,
        "export_profile_map",
        return_value=(None, "no_profile_map"),
    ):
        response = job_routes.export_profile_map("j1", username="alice")

    assert _status(response) == 404


class TestProfileMapDownloadSurvivesStorageFailure:
    """A download must not be lost because the CACHE write failed.

    export_profile_map() builds the workbook bytes first and only then tries to
    cache them to disk; a failure writing that cache (a full disk, a permissions
    problem) must not cost the user a download whose content had already been
    built successfully in memory.
    """

    def test_the_workbook_is_kept_when_the_disk_cache_write_fails(self, monkeypatch):
        from services import job_service as module
        from services.job_service import JobService
        from unittest.mock import MagicMock

        repository = MagicMock()
        repository.get.return_value = {"job_id": "j1", "created_by": "alice"}
        service = JobService(repository=repository)

        monkeypatch.setattr(
            module.profile_map_repository, "get", lambda job_id: {"rows": []}
        )

        def unwritable_path(job_id):
            path = MagicMock()
            path.write_bytes.side_effect = OSError("disk full")
            return path

        monkeypatch.setattr(
            "core.storage_layout.get_profile_map_job_path", unwritable_path
        )

        filename, reason = service.export_profile_map("j1", requester="alice")

        # The caller is told the cache is cold, not that the export failed...
        assert reason == "ok_uncached"
        assert filename.endswith(".xlsx")
        # ...and the bytes are still available to serve.
        assert service.last_exported_workbook
        assert service.last_exported_workbook[:2] == b"PK"  # a real .xlsx (zip)
