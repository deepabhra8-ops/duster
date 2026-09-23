from __future__ import annotations

import asyncio
from unittest.mock import patch

from routes.metadata_routes import metadata
from services.connectors.salesforce_connector import SalesforceConnector


class _FakeRequest:
    def __init__(self, body: dict):
        self._body = body

    async def json(self):
        return self._body


def _call(body: dict):
    return asyncio.run(metadata(_FakeRequest(body)))


def test_missing_database_type_is_rejected():
    response = _call({"connectionDetails": {}, "level": "schemas"})
    assert response.status_code == 400


def test_missing_connection_details_is_rejected():
    response = _call({"databaseType": "postgresql", "level": "schemas"})
    assert response.status_code == 400


def test_invalid_level_is_rejected():
    response = _call(
        {"databaseType": "postgresql", "connectionDetails": {"host": "h"}, "level": "bogus"}
    )
    assert response.status_code == 400


def test_generic_sql_connector_still_requires_schema_for_tables():
    response = _call(
        {"databaseType": "postgresql", "connectionDetails": {"host": "h"}, "level": "tables"}
    )
    assert response.status_code == 400
    assert "schema is required" in response.body.decode()


def test_salesforce_schemas_returns_the_single_logical_schema():
    result = _call(
        {
            "databaseType": "salesforce",
            "connectionDetails": {"username": "u"},
            "level": "schemas",
        }
    )
    assert result == {"ok": True, "items": ["Salesforce"]}


def test_salesforce_tables_does_not_require_a_schema_first():
    with patch.object(SalesforceConnector, "get_objects", return_value=["Account", "Contact"]):
        result = _call(
            {
                "databaseType": "salesforce",
                "connectionDetails": {"username": "u"},
                "level": "tables",
            }
        )
    assert result == {"ok": True, "items": ["Account", "Contact"]}


def test_salesforce_columns_applies_the_search_filter():
    with patch.object(
        SalesforceConnector, "get_fields", return_value=["Id", "Name", "Industry"]
    ):
        result = _call(
            {
                "databaseType": "salesforce",
                "connectionDetails": {"username": "u"},
                "level": "columns",
                "table": "Account",
                "search": "ind",
            }
        )
    assert result == {"ok": True, "items": ["Industry"]}


def test_salesforce_columns_still_requires_a_table():
    response = _call(
        {
            "databaseType": "salesforce",
            "connectionDetails": {"username": "u"},
            "level": "columns",
        }
    )
    assert response.status_code == 400
