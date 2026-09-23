"""Unit tests for ConfigBuilder's connector-polymorphic dispatch - the core of the OCP
refactor: which accelerator data source, which extra credentials, and whether curation-mode
staging is allowed are now all resolved by asking the connector, not by branching on
databaseType inline in ConfigBuilder.
"""
from __future__ import annotations

import pytest

import core.storage_layout as paths
from services.config_builder import config_builder


@pytest.fixture(autouse=True)
def isolate_job_filesystem(tmp_path, monkeypatch):
    """Redirect every job/profile-map path ConfigBuilder touches into a temp directory, so
    these tests never write into the real runtime/ folder."""
    jobs_dir = tmp_path / "jobs"
    profile_map_uploads_dir = tmp_path / "uploads" / "profile_map"
    jobs_dir.mkdir(parents=True)
    profile_map_uploads_dir.mkdir(parents=True)

    monkeypatch.setattr(paths, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(paths, "PROFILE_MAP_UPLOADS_DIR", profile_map_uploads_dir)


SALESFORCE_PARAMS = {
    "source_type": "database",
    "databaseType": "salesforce",
    "connectionDetails": {
        "username": "u",
        "password": "p",
        "security_token": "t",
        "domain": "login",
    },
    "tables": [{"name": "Account"}],
}

POSTGRES_PARAMS = {
    "source_type": "database",
    "databaseType": "postgresql",
    "connectionDetails": {
        "host": "db.example.com",
        "username": "u",
        "password": "p",
    },
    "tables": [{"name": "customers"}],
}


def test_salesforce_uses_its_own_accelerator_source_type():
    config = config_builder.build("job-sf-1", {**SALESFORCE_PARAMS, "run_mode": 1})
    assert config["source"]["type"] == "salesforce"


def test_salesforce_source_db_carries_raw_credentials():
    config = config_builder.build("job-sf-2", {**SALESFORCE_PARAMS, "run_mode": 1})
    assert config["source"]["db"] == {
        "connection_string": "salesforce://simple-salesforce",
        "username": "u",
        "password": "p",
        "security_token": "t",
        "domain": "login",
    }


def test_salesforce_curation_mode_still_falls_back_to_csv_staging():
    """Salesforce opts out of database staging via supports_database_staging() - this must
    hold even when the job explicitly asks for curation mode (run_mode=2)."""
    config = config_builder.build("job-sf-3", {**SALESFORCE_PARAMS, "run_mode": 2})
    assert config["staging"]["type"] == "csv"


def test_postgres_uses_the_generic_accelerator_source_type():
    config = config_builder.build("job-pg-1", {**POSTGRES_PARAMS, "run_mode": 1})
    assert config["source"]["type"] == "database"


def test_postgres_source_db_has_no_extra_accelerator_credentials():
    """Postgres doesn't override accelerator_credentials() - nothing beyond
    connection_string should appear. This is the parity check that the refactor didn't
    change behavior for connectors that already worked."""
    config = config_builder.build("job-pg-2", {**POSTGRES_PARAMS, "run_mode": 1})
    assert set(config["source"]["db"].keys()) == {"connection_string"}


def test_postgres_curation_mode_still_uses_database_staging():
    """The case Salesforce is the exception to: every other connector must keep staging to
    the database in curation mode exactly as before the refactor."""
    config = config_builder.build("job-pg-3", {**POSTGRES_PARAMS, "run_mode": 2})
    assert config["staging"]["type"] == "database"
    assert "connection_string" in config["staging"]["db"]


def test_bigquery_staging_carries_its_accelerator_credentials():
    params = {
        "source_type": "database",
        "databaseType": "bigquery",
        "connectionDetails": {
            "project_id": "p",
            "dataset_id": "d",
            "service_account_json": "{}",
        },
        "tables": [{"name": "events"}],
        "run_mode": 2,
    }
    config = config_builder.build("job-bq-1", params)
    assert config["staging"]["type"] == "database"
    assert config["staging"]["db"]["project_id"] == "p"
    assert config["staging"]["db"]["dataset_id"] == "d"


def test_unrecognized_database_type_falls_back_to_generic_behavior():
    """No connector is registered for this type - ConfigBuilder must degrade gracefully
    (generic accelerator type, no crash) instead of assuming any specific connector's shape."""
    params = {
        "source_type": "database",
        "databaseType": "some_future_connector_not_yet_registered",
        "connectionDetails": {"host": "h"},
        "tables": [{"name": "t"}],
        "run_mode": 1,
    }
    config = config_builder.build("job-unknown-1", params)
    assert config["source"]["type"] == "database"
