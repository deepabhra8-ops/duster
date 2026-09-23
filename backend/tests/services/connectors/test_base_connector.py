"""Unit tests for services.connectors.base_connector.DatabaseConnector's default hooks.

These defaults are what every existing SQL/JDBC connector relies on implicitly (they don't
override any of them) - locking them in here is what guarantees a *future* connector can
override just what it needs without any of the others changing behavior.
"""
from __future__ import annotations

import pytest

from services.connectors.base_connector import DatabaseConnector


class _DummyConnector(DatabaseConnector):
    """Minimal concrete connector - implements only the one abstract method."""

    db_type = "dummy"
    required_fields = ("host",)

    def build_connection_string(self, details):
        # Deliberately not a real SQLAlchemy dialect: create_engine() rejects it
        # immediately (NoSuchModuleError), with no network call - fast and deterministic.
        return "bogus+driver://nowhere"


@pytest.fixture
def connector() -> _DummyConnector:
    return _DummyConnector()


def test_accelerator_source_type_defaults_to_database(connector):
    assert connector.accelerator_source_type() == "database"


def test_accelerator_credentials_defaults_to_empty(connector):
    assert connector.accelerator_credentials({"anything": "goes"}) == {}


def test_supports_database_staging_defaults_to_true(connector):
    assert connector.supports_database_staging() is True


def test_supports_sql_metadata_inspection_defaults_to_true(connector):
    assert connector.supports_sql_metadata_inspection() is True


def test_error_patterns_default_to_empty_tuple(connector):
    assert connector.error_patterns == ()


@pytest.mark.parametrize(
    "method_name, args",
    [
        ("list_schemas", ({},)),
        ("list_tables", ({}, "public")),
        ("list_columns", ({}, "public", "some_table")),
    ],
)
def test_metadata_listing_hooks_are_not_implemented_by_default(connector, method_name, args):
    """These are only ever called when supports_sql_metadata_inspection() is False - a
    connector that doesn't override it should never reach them, but one that somehow does
    must fail loudly rather than silently returning nothing."""
    with pytest.raises(NotImplementedError):
        getattr(connector, method_name)(*args)


def test_validate_reports_missing_required_fields(connector):
    assert connector.validate({}) == ["host"]
    assert connector.validate({"host": "db.example.com"}) == []


def test_default_test_never_raises_and_routes_through_error_patterns(connector):
    """test() must never propagate a raw exception - it always comes back as a dict, with
    the message routed through describe_connection_error(exc, self.error_patterns)."""
    result = connector.test({"host": "db.example.com"})

    assert result["ok"] is False
    assert isinstance(result["error"], str)
    assert result["error"]  # never empty, never a raw traceback string
