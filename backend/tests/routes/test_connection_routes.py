from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from routes import connection_routes
from services.saved_connection_service import ConnectionPermissionError


class _FakeRequest:
    def __init__(self, body=None, query=None):
        self._body = body
        self.query_params = query or {}

    async def json(self):
        return self._body


def _body(response):
    if isinstance(response, dict):
        return response

    return json.loads(response.body)


def _status(response):
    return getattr(response, "status_code", 200)


SUMMARY = {
    "id": "abc123",
    "name": "Warehouse",
    "db_type": "postgresql",
    "description": "",
    "port": 5432,
    "created_by": "alice",
}


def test_list_returns_non_secret_fields():
    with patch.object(
        connection_routes.saved_connection_service, "list_all", return_value=[SUMMARY]
    ):
        response = connection_routes.list_connections(_FakeRequest())

    body = _body(response)
    assert body["ok"] is True
    assert body["data"] == [SUMMARY]
    assert "connection_details_encrypted" not in json.dumps(body)


def test_list_paginates_when_a_page_is_asked_for():
    page = {"connections": [SUMMARY], "total": 1, "totalPages": 1}

    with patch.object(
        connection_routes.saved_connection_service, "list_page", return_value=page
    ) as list_page:
        response = connection_routes.list_connections(
            _FakeRequest(query={"page": "2", "pageSize": "5", "search": "ware"})
        )

    body = _body(response)
    assert body["ok"] is True
    assert body["total"] == 1
    assert list_page.call_args.kwargs["page"] == 2
    assert list_page.call_args.kwargs["page_size"] == 5
    assert list_page.call_args.kwargs["search"] == "ware"
    assert "connection_details_encrypted" not in json.dumps(body)


def test_list_rejects_a_non_numeric_page():
    response = connection_routes.list_connections(_FakeRequest(query={"page": "abc"}))

    assert _status(response) == 400


def test_list_rejects_a_page_below_one():
    response = connection_routes.list_connections(
        _FakeRequest(query={"page": "0", "pageSize": "10"})
    )

    assert _status(response) == 400


def test_create_uses_authenticated_user_as_owner():
    with patch.object(
        connection_routes.saved_connection_service, "create", return_value=SUMMARY
    ) as create:
        response = asyncio.run(
            connection_routes.create_connection(
                _FakeRequest(
                    {
                        "name": "Warehouse",
                        "databaseType": "postgresql",
                        "connectionDetails": {"host": "h"},
                    }
                ),
                username="alice",
            )
        )

    assert _body(response)["ok"] is True
    assert create.call_args.kwargs["created_by"] == "alice"


def test_create_maps_validation_error_to_400():
    with patch.object(
        connection_routes.saved_connection_service,
        "create",
        side_effect=ValueError("Missing required fields: host"),
    ):
        response = asyncio.run(
            connection_routes.create_connection(_FakeRequest({}), username="alice")
        )

    assert _status(response) == 400
    assert "Missing required fields" in _body(response)["error"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: asyncio.run(
            connection_routes.update_connection(
                "abc123", _FakeRequest({"name": "x"}), username="bob"
            )
        ),
        lambda: connection_routes.delete_connection("abc123", username="bob"),
        lambda: connection_routes.reveal_connection("abc123", username="bob"),
    ],
)
def test_non_owner_gets_403(call):
    denied = ConnectionPermissionError("Only the user who created this connection can edit it.")

    with patch.object(
        connection_routes.saved_connection_service, "update", side_effect=denied
    ), patch.object(
        connection_routes.saved_connection_service, "delete", side_effect=denied
    ), patch.object(
        connection_routes.saved_connection_service, "reveal", side_effect=denied
    ):
        response = call()

    assert _status(response) == 403
    assert _body(response)["ok"] is False


def test_update_missing_connection_is_404():
    with patch.object(
        connection_routes.saved_connection_service, "update", return_value=None
    ):
        response = asyncio.run(
            connection_routes.update_connection(
                "nope", _FakeRequest({"name": "x"}), username="alice"
            )
        )

    assert _status(response) == 404


def test_delete_missing_connection_is_404():
    with patch.object(
        connection_routes.saved_connection_service, "delete", return_value=False
    ):
        response = connection_routes.delete_connection("nope", username="alice")

    assert _status(response) == 404


def test_reveal_returns_decrypted_details_for_owner():
    with patch.object(
        connection_routes.saved_connection_service,
        "reveal",
        return_value={"connection_details": {"host": "h", "password": "s3cr3t"}},
    ):
        response = connection_routes.reveal_connection("abc123", username="alice")

    body = _body(response)
    assert body["ok"] is True
    assert body["data"]["connection_details"]["password"] == "s3cr3t"


def test_reveal_surfaces_rotated_key_error():
    with patch.object(
        connection_routes.saved_connection_service,
        "reveal",
        side_effect=ValueError("Stored connection details could not be decrypted"),
    ):
        response = connection_routes.reveal_connection("abc123", username="alice")

    assert _status(response) == 500
    assert "could not be decrypted" in _body(response)["error"]


def test_schemas_are_read_live_from_the_source():
    with patch.object(
        connection_routes.saved_connection_service,
        "list_schemas",
        return_value=["public", "analytics"],
    ) as live:
        response = connection_routes.list_connection_schemas("abc123")

    live.assert_called_once_with("abc123")
    assert _body(response)["schemas"] == ["public", "analytics"]


def test_schemas_missing_connection_is_404():
    with patch.object(
        connection_routes.saved_connection_service, "list_schemas", return_value=None
    ):
        response = connection_routes.list_connection_schemas("nope")

    assert _status(response) == 404


def test_schemas_report_a_failure_without_leaking_driver_text():
    raw = "could not connect to db-prod-01.internal:5432"

    with patch.object(
        connection_routes.saved_connection_service,
        "list_schemas",
        side_effect=RuntimeError(raw),
    ):
        response = connection_routes.list_connection_schemas("abc123")

    error = _body(response)["error"]

    assert _status(response) == 400
    assert raw not in error
    assert "db-prod-01.internal" not in error
    assert error


def test_refresh_is_an_alias_of_the_live_read():
    with patch.object(
        connection_routes.saved_connection_service,
        "list_schemas",
        return_value=["public"],
    ):
        response = connection_routes.refresh_connection_schemas("abc123")

    assert _body(response)["schemas"] == ["public"]


def test_saving_a_connection_does_no_catalog_work():
    import asyncio

    created = {"id": "abc123", "name": "Warehouse", "db_type": "postgresql"}

    with patch.object(
        connection_routes.saved_connection_service, "create", return_value=created
    ):
        with patch.object(
            connection_routes.saved_connection_service, "list_schemas"
        ) as scan:
            response = asyncio.run(
                connection_routes.create_connection(
                    _FakeRequest({"name": "Warehouse", "databaseType": "postgresql"}),
                    username="tester",
                )
            )

    scan.assert_not_called()
    assert response["data"] == created
    assert "schemas" not in response["data"]
    assert "schemas_error" not in response
def test_tables_requires_a_schema():
    response = connection_routes.list_connection_tables("abc123", schema="")

    assert _status(response) == 400


def test_tables_returns_one_schemas_tables():
    with patch.object(
        connection_routes.saved_connection_service,
        "list_tables",
        return_value=["claim", "member"],
    ) as list_tables:
        response = connection_routes.list_connection_tables("abc123", schema="public")

    list_tables.assert_called_once_with("abc123", "public")
    assert _body(response)["tables"] == ["claim", "member"]


def test_columns_requires_schema_and_table():
    assert _status(connection_routes.list_connection_columns("c", "", "t")) == 400
    assert _status(connection_routes.list_connection_columns("c", "s", "")) == 400


def test_columns_returns_one_tables_columns():
    with patch.object(
        connection_routes.saved_connection_service,
        "list_columns",
        return_value=["claim_id", "amount"],
    ) as list_columns:
        response = connection_routes.list_connection_columns(
            "abc123", schema="public", table="claim"
        )

    list_columns.assert_called_once_with("abc123", "public", "claim")
    assert _body(response)["columns"] == ["claim_id", "amount"]
