from __future__ import annotations

import io
import zipfile
from typing import Any

import polars as pl

from core.storage_layout import get_staging_dir
from services.connection_service import connection_service
from utils.logger import get_logger


logger = get_logger(__name__)


class StagingExportError(Exception):
    status_code = 404


class StagingConnectionError(StagingExportError):
    status_code = 400


class StagingQueryError(StagingExportError):
    status_code = 500


class StagingExportService:
    def export(
        self,
        job_id: str,
        params: dict[str, Any],
    ) -> io.BytesIO:
        csv_archive = self._export_csv_staging(job_id)

        if csv_archive is not None:
            return csv_archive

        source_type = params.get("source_type", "csv")

        if source_type == "database":
            return self._export_database_staging(params)

        raise StagingExportError("No staging output found")

    def _export_csv_staging(
        self,
        job_id: str,
    ) -> io.BytesIO | None:
        staging_dir = get_staging_dir(job_id)

        if not staging_dir.is_dir():
            return None

        csv_files = sorted(staging_dir.glob("*.csv"))

        if not csv_files:
            return None

        buffer = io.BytesIO()

        with zipfile.ZipFile(
            buffer,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as archive:
            for file_path in csv_files:
                archive.write(file_path, file_path.name)

        buffer.seek(0)
        return buffer

    def _export_database_staging(
        self,
        params: dict[str, Any],
    ) -> io.BytesIO:
        try:
            connection_string = connection_service.resolve_connection_string(
                params
            )
        except Exception as exc:
            raise StagingConnectionError(str(exc)) from exc

        try:
            from sqlalchemy import create_engine, inspect

            engine = create_engine(connection_string)
            inspector = inspect(engine)
            tables = inspector.get_table_names(schema="staging")

            buffer = io.BytesIO()

            with zipfile.ZipFile(
                buffer,
                "w",
                zipfile.ZIP_DEFLATED,
            ) as archive:
                for table in tables:
                    quoted = table.replace('"', '""')

                    with engine.connect() as connection:
                        dataframe = pl.read_database(
                            query=f'SELECT * FROM "staging"."{quoted}"',
                            connection=connection,
                        )

                    archive.writestr(
                        f"{table}_staging.csv",
                        dataframe.write_csv().encode("utf-8"),
                    )

            buffer.seek(0)
            return buffer

        except Exception as exc:
            logger.exception("Failed to export database staging")
            raise StagingQueryError(
                f"Could not export DB staging: {exc}"
            ) from exc


staging_export_service = StagingExportService()
