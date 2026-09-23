"""Unit tests for MetadataScanService - per-level catalog lookups.

The service deliberately does not walk a whole catalog: schemas, then one schema's
tables, then one table's columns, each fetched only when opened. These tests pin
that boundary, since regressing to a full walk is exactly what made saving a
connection slow on a large database.

No real database is touched: the SQLAlchemy path goes through a patched engine
cache and inspector, the connector path through a stub connector.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.metadata_scan_service import MetadataScanService


DETAILS = {"host": "db.example.com", "username": "u", "password": "p"}
MODULE = "services.metadata_scan_service"


@pytest.fixture
def service() -> MetadataScanService:
    return MetadataScanService()


def _sql_patches(inspector):
    """Patch everything outside the service on the SQLAlchemy path."""
    return (
        patch(f"{MODULE}.connector_registry.get", return_value=None),
        patch(
            f"{MODULE}.connection_service.build_connection_string",
            return_value="postgresql+psycopg2://u:p@h/db",
        ),
        patch(f"{MODULE}.get_cached_engine", return_value=MagicMock()),
        patch(f"{MODULE}.inspect", return_value=inspector),
    )


def _run(fn, inspector):
    patches = _sql_patches(inspector)
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in patches:
            p.stop()


# ── input validation ────────────────────────────────────────────────


def test_requires_database_type(service):
    with pytest.raises(ValueError, match="databaseType is required"):
        service.list_schemas("", DETAILS)


def test_requires_connection_details(service):
    with pytest.raises(ValueError, match="connectionDetails is required"):
        service.list_schemas("postgresql", {})


def test_tables_requires_schema(service):
    with pytest.raises(ValueError, match="schema is required"):
        service.list_tables("postgresql", DETAILS, "")


def test_columns_requires_table(service):
    with pytest.raises(ValueError, match="table is required"):
        service.list_columns("postgresql", DETAILS, "public", "")


# ── schemas ─────────────────────────────────────────────────────────


def test_list_schemas_does_not_touch_tables_or_columns(service):
    """The whole point: saving a connection must not enumerate the catalog."""
    inspector = MagicMock()
    inspector.get_schema_names.return_value = ["public", "analytics"]

    result = _run(lambda: service.list_schemas("postgresql", DETAILS), inspector)

    assert result == ["analytics", "public"]  # sorted
    inspector.get_table_names.assert_not_called()
    inspector.get_columns.assert_not_called()


def test_list_schemas_dedupes_and_drops_blanks(service):
    inspector = MagicMock()
    inspector.get_schema_names.return_value = ["public", " public ", "", None, "ops"]

    result = _run(lambda: service.list_schemas("postgresql", DETAILS), inspector)

    assert result == ["ops", "public"]


def test_list_schemas_respects_cap(service):
    inspector = MagicMock()
    inspector.get_schema_names.return_value = [f"s{i:02d}" for i in range(10)]

    with patch(f"{MODULE}.METADATA_SCAN_MAX_SCHEMAS", 3):
        result = _run(lambda: service.list_schemas("postgresql", DETAILS), inspector)

    assert len(result) == 3


def test_reuses_cached_engine_and_never_disposes_it(service):
    """A fresh engine per dropdown would mean a fresh login each time, which is
    what previously tripped a database's failed-login lockout."""
    inspector = MagicMock()
    inspector.get_schema_names.return_value = []
    engine = MagicMock()

    with patch(f"{MODULE}.connector_registry.get", return_value=None), patch(
        f"{MODULE}.connection_service.build_connection_string",
        return_value="postgresql+psycopg2://u:p@h/db",
    ), patch(f"{MODULE}.get_cached_engine", return_value=engine) as cached, patch(
        f"{MODULE}.inspect", return_value=inspector
    ):
        service.list_schemas("postgresql", DETAILS)

    cached.assert_called_once()
    engine.dispose.assert_not_called()


# ── tables ──────────────────────────────────────────────────────────


def test_list_tables_scoped_to_one_schema(service):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["claim", "member"]
    inspector.get_view_names.return_value = []

    result = _run(
        lambda: service.list_tables("postgresql", DETAILS, "public"), inspector
    )

    assert result == ["claim", "member"]
    inspector.get_table_names.assert_called_once_with(schema="public")


def test_list_tables_includes_views(service):
    """Views are valid profiling targets."""
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["claim"]
    inspector.get_view_names.return_value = ["claim_summary"]

    result = _run(
        lambda: service.list_tables("postgresql", DETAILS, "public"), inspector
    )

    assert result == ["claim", "claim_summary"]


def test_list_tables_tolerates_dialect_without_view_reflection(service):
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["claim"]
    inspector.get_view_names.side_effect = NotImplementedError

    result = _run(
        lambda: service.list_tables("postgresql", DETAILS, "public"), inspector
    )

    assert result == ["claim"]


def test_list_tables_respects_cap(service):
    inspector = MagicMock()
    inspector.get_table_names.return_value = [f"t{i:02d}" for i in range(10)]
    inspector.get_view_names.return_value = []

    with patch(f"{MODULE}.METADATA_SCAN_MAX_TABLES_PER_SCHEMA", 4):
        result = _run(
            lambda: service.list_tables("postgresql", DETAILS, "public"), inspector
        )

    assert len(result) == 4


# ── columns ─────────────────────────────────────────────────────────


def test_list_columns_scoped_to_one_table(service):
    inspector = MagicMock()
    inspector.get_columns.return_value = [{"name": "claim_id"}, {"name": "amount"}]

    result = _run(
        lambda: service.list_columns("postgresql", DETAILS, "public", "claim"),
        inspector,
    )

    assert result == ["amount", "claim_id"]
    inspector.get_columns.assert_called_once_with("claim", schema="public")


# ── connector path (no SQLAlchemy dialect, e.g. Salesforce) ─────────


def _stub_connector():
    connector = MagicMock()
    connector.supports_sql_metadata_inspection.return_value = False
    connector.list_schemas.return_value = ["Salesforce"]
    connector.list_tables.return_value = ["Account", "Contact"]
    connector.list_columns.return_value = ["Id", "Name"]
    return connector


def test_connector_path_used_when_no_sql_dialect(service):
    connector = _stub_connector()

    with patch(f"{MODULE}.connector_registry.get", return_value=connector):
        assert service.list_schemas("salesforce", DETAILS) == ["Salesforce"]
        assert service.list_tables("salesforce", DETAILS, "Salesforce") == [
            "Account",
            "Contact",
        ]
        assert service.list_columns("salesforce", DETAILS, "Salesforce", "Account") == [
            "Id",
            "Name",
        ]


def test_sql_dialect_connector_still_uses_generic_inspection(service):
    """A connector that *does* have a dialect must not take the connector path."""
    connector = MagicMock()
    connector.supports_sql_metadata_inspection.return_value = True

    inspector = MagicMock()
    inspector.get_schema_names.return_value = ["public"]

    with patch(f"{MODULE}.connector_registry.get", return_value=connector), patch(
        f"{MODULE}.connection_service.build_connection_string",
        return_value="postgresql+psycopg2://u:p@h/db",
    ), patch(f"{MODULE}.get_cached_engine", return_value=MagicMock()), patch(
        f"{MODULE}.inspect", return_value=inspector
    ):
        assert service.list_schemas("postgresql", DETAILS) == ["public"]

    connector.list_schemas.assert_not_called()
