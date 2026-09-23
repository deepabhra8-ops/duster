from __future__ import annotations

import pytest

from services.connection_service import ConnectionService


@pytest.fixture
def service() -> ConnectionService:
    return ConnectionService()


def test_build_connection_string_delegates_to_the_registered_connector(service):
    connection_string = service.build_connection_string(
        "postgresql",
        {"host": "db.example.com", "username": "u", "password": "p"},
    )
    assert connection_string.startswith("postgresql+psycopg2://")


def test_build_connection_string_raises_for_an_unknown_type(service):
    with pytest.raises(ValueError, match="Unsupported database type"):
        service.build_connection_string("not_a_real_db", {})


def test_resolve_connection_string_prefers_database_type_and_details(service):
    params = {
        "databaseType": "postgresql",
        "connectionDetails": {"host": "h", "username": "u", "password": "p"},
        "connection_string": "should-be-ignored",
    }
    result = service.resolve_connection_string(params)
    assert result.startswith("postgresql+psycopg2://")


def test_resolve_connection_string_falls_back_to_a_legacy_connection_string(service):
    params = {"connection_string": "postgresql://legacy"}
    assert service.resolve_connection_string(params) == "postgresql://legacy"


def test_resolve_connection_string_raises_when_nothing_is_available(service):
    with pytest.raises(ValueError, match="not available"):
        service.resolve_connection_string({})


def test_validate_connection_details_reports_missing_fields(service):
    missing = service.validate_connection_details("postgresql", {})
    assert "host" in missing


def test_validate_connection_details_returns_empty_for_an_unknown_type(service):
    assert service.validate_connection_details("not_a_real_db", {}) == []


def test_test_connection_requires_a_database_type(service):
    result = service.test_connection("", {})
    assert result == {"ok": False, "error": "databaseType is required"}


def test_test_connection_rejects_an_unknown_database_type(service):
    result = service.test_connection("not_a_real_db", {})
    assert result["ok"] is False
    assert "Unsupported database type" in result["error"]


def test_test_connection_reports_missing_required_fields_before_attempting_a_connection(
    service,
):
    result = service.test_connection("postgresql", {})
    assert result["ok"] is False
    assert "Missing required fields" in result["error"]
    assert "host" in result["error"]


def test_test_connection_string_returns_a_friendly_error_for_a_bogus_dialect(service):
    result = service.test_connection_string("bogus+driver://nowhere")
    assert result["ok"] is False
    assert isinstance(result["error"], str)
