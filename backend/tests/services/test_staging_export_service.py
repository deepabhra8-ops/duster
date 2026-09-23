from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import services.staging_export_service as staging_export_module
from services.staging_export_service import (
    StagingConnectionError,
    StagingExportError,
    StagingExportService,
)


@pytest.fixture
def service() -> StagingExportService:
    return StagingExportService()


@pytest.fixture(autouse=True)
def redirect_staging_dir(tmp_path, monkeypatch):
    def fake_get_staging_dir(job_id):
        return tmp_path / job_id

    monkeypatch.setattr(staging_export_module, "get_staging_dir", fake_get_staging_dir)
    return tmp_path


def test_export_zips_csv_staging_files_when_present(service, redirect_staging_dir):
    staging_dir = redirect_staging_dir / "job-1"
    staging_dir.mkdir()
    (staging_dir / "customers_clean.csv").write_bytes(b"id,name\n1,Alice\n")

    buffer = service.export("job-1", params={})

    with zipfile.ZipFile(buffer) as archive:
        assert archive.namelist() == ["customers_clean.csv"]
        assert archive.read("customers_clean.csv") == b"id,name\n1,Alice\n"


def test_export_ignores_a_staging_directory_with_no_csv_files(service, redirect_staging_dir):
    staging_dir = redirect_staging_dir / "job-2"
    staging_dir.mkdir()
    (staging_dir / "readme.txt").write_text("not a csv")

    with pytest.raises(StagingExportError):
        service.export("job-2", params={"source_type": "csv"})


def test_export_falls_back_to_database_staging_when_no_csv_output_exists(service):
    with patch.object(
        StagingExportService,
        "_export_database_staging",
        return_value=BytesIO(b"zip-bytes"),
    ) as mock_export_db:
        result = service.export("job-3", params={"source_type": "database"})

    mock_export_db.assert_called_once()
    assert result.read() == b"zip-bytes"


def test_export_raises_when_nothing_is_found_and_the_source_is_not_a_database(service):
    with pytest.raises(StagingExportError, match="No staging output found"):
        service.export("job-4", params={"source_type": "csv"})


def test_export_database_staging_wraps_connection_resolution_failures(service):
    with patch.object(
        staging_export_module.connection_service,
        "resolve_connection_string",
        side_effect=ValueError("no connection info"),
    ):
        with pytest.raises(StagingConnectionError):
            service._export_database_staging(params={})


def test_export_database_staging_zips_one_csv_per_staging_table(service):
    fake_inspector = MagicMock()
    fake_inspector.get_table_names.return_value = ["customers", "orders"]

    with patch.object(
        staging_export_module.connection_service,
        "resolve_connection_string",
        return_value="postgresql://fake",
    ), patch("sqlalchemy.create_engine", return_value=MagicMock()), patch(
        "sqlalchemy.inspect", return_value=fake_inspector
    ), patch(
        "pandas.read_sql", return_value=pd.DataFrame({"id": [1]})
    ):
        buffer = service._export_database_staging(params={"databaseType": "postgresql"})

    with zipfile.ZipFile(buffer) as archive:
        assert set(archive.namelist()) == {"customers_staging.csv", "orders_staging.csv"}


def test_export_database_staging_wraps_query_failures(service):
    with patch.object(
        staging_export_module.connection_service,
        "resolve_connection_string",
        return_value="postgresql://fake",
    ), patch("sqlalchemy.create_engine", side_effect=RuntimeError("boom")):
        from services.staging_export_service import StagingQueryError

        with pytest.raises(StagingQueryError):
            service._export_database_staging(params={})
