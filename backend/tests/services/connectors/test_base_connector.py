from __future__ import annotations

import pytest

from services.connectors.base_connector import DatabaseConnector


class _DummyConnector(DatabaseConnector):
    db_type = "dummy"
    required_fields = ("host",)

    def build_connection_string(self, details):
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
    with pytest.raises(NotImplementedError):
        getattr(connector, method_name)(*args)


def test_validate_reports_missing_required_fields(connector):
    assert connector.validate({}) == ["host"]
    assert connector.validate({"host": "db.example.com"}) == []


def test_default_test_never_raises_and_routes_through_error_patterns(connector):
    result = connector.test({"host": "db.example.com"})

    assert result["ok"] is False
    assert isinstance(result["error"], str)
    assert result["error"]
