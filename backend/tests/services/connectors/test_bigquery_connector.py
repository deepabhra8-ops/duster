"""Unit tests for BigqueryConnector.accelerator_credentials() - the other half of the
config_builder if/else branch removed during the OCP refactor - plus regression locks
confirming it still relies on DatabaseConnector's other defaults unchanged.
"""
from __future__ import annotations

from services.connectors.bigquery_connector import BigqueryConnector


DETAILS = {
    "project_id": "my-project",
    "dataset_id": "my_dataset",
    "service_account_json": '{"type": "service_account"}',
}


def test_accelerator_credentials_returns_service_account_fields():
    connector = BigqueryConnector()
    assert connector.accelerator_credentials(DETAILS) == {
        "service_account_json": DETAILS["service_account_json"],
        "project_id": DETAILS["project_id"],
        "dataset_id": DETAILS["dataset_id"],
    }


def test_accelerator_credentials_defaults_missing_fields_to_empty_strings():
    connector = BigqueryConnector()
    assert connector.accelerator_credentials({}) == {
        "service_account_json": "",
        "project_id": "",
        "dataset_id": "",
    }


def test_still_supports_database_staging_by_default():
    """Unlike Salesforce, BigQuery IS a valid staging target (via Spark's dedicated
    format("bigquery") writer) - it must not have overridden this default."""
    assert BigqueryConnector().supports_database_staging() is True


def test_still_supports_generic_sql_metadata_inspection_by_default():
    """BigQuery has a real SQLAlchemy dialect (bigquery://project/dataset), so it keeps
    using the generic inspector rather than needing its own list_* methods."""
    assert BigqueryConnector().supports_sql_metadata_inspection() is True


def test_build_connection_string_still_works():
    connector = BigqueryConnector()
    assert connector.build_connection_string(DETAILS) == "bigquery://my-project/my_dataset"


def test_validate_requires_service_account_json_in_addition_to_base_fields():
    connector = BigqueryConnector()
    missing = connector.validate({"project_id": "p", "dataset_id": "d"})
    assert missing == ["service_account_json"]
