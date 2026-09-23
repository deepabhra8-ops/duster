from pathlib import Path
from typing import Any

from core.storage_layout import (
    ensure_job_directory,
    get_job_dir,
    get_profile_map_job_path,
    get_report_job_path,
    get_reports_dir,
    get_staging_dir,
)
from core.config import (
    ACCEL_PATH,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PROJECT_NAME,
    DEFAULT_RUN_MODE,
)
from services.connection_service import connection_service
from services.connectors import connector_registry
from services.lov_service import lov_service
from utils.logger import get_logger


logger = get_logger(__name__)


class ConfigBuilder:
    def build(
        self,
        job_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        job_dir = ensure_job_directory(job_id)

        run_mode = int(
            params.get(
                "run_mode",
                DEFAULT_RUN_MODE,
            )
        )

        project = params.get(
            "project_name",
            DEFAULT_PROJECT_NAME,
        )

        connection_string = self._build_connection_string(params)

        tables = self._build_tables(params)

        profile_map_path = self.resolve_profile_map_path(
            job_id,
            params,
        )

        lov_file = str(params.get("lov_file", "") or "")

        lov_configuration = (
            lov_service.build_lov_configuration(
                profile_map_path,
                lov_file=lov_file or None,
            )
        )

        staging_configuration = self._build_staging_configuration(
            job_id,
            run_mode,
            connection_string,
            params,
        )

        accelerator_source_type = self._resolve_accelerator_source_type(params)

        resolved = self.resolve_connection(params)

        source_db = {
            "connection_string": connection_string,
            **self._accelerator_credentials(
                {**params, "databaseType": resolved["databaseType"]},
                resolved["connectionDetails"],
            ),
        }

        configuration = {
            "job_id": job_id,
            "project_name": project,
            "run_mode": run_mode,
            "source": {
                "type": accelerator_source_type,
                "base_path": "",
                "chunk_size": int(
                    params.get(
                        "chunk_size",
                        DEFAULT_CHUNK_SIZE,
                    )
                ),
                "tables": tables,
                "db": source_db,
            },
            "staging": staging_configuration,
            "profile_map_file": (
                profile_map_path.as_posix()
                if profile_map_path
                else ""
            ),
            "reports": {
                "output_path": get_reports_dir(job_id).as_posix() + "/",
                "report_file": get_report_job_path(job_id).as_posix(),
            },
            "lov_tables": lov_configuration,
            "lov_file": lov_file,
        }

        source_job_id = params.get("profile_map_source_job_id")

        if source_job_id:
            configuration["profile_map_source_job_id"] = source_job_id

        return configuration

    def _get_connector(
        self,
        params: dict[str, Any],
    ):
        database_type = str(
            params.get("databaseType", "")
        ).strip().lower()

        return connector_registry.get(database_type)

    def _accelerator_credentials(
        self,
        params: dict[str, Any],
        connection_details: dict[str, Any],
    ) -> dict[str, Any]:
        connector = self._get_connector(params)

        if connector is None:
            return {}

        return connector.accelerator_credentials(connection_details)

    def _resolve_accelerator_source_type(
        self,
        params: dict[str, Any],
    ) -> str:
        connector = self._get_connector(params)

        if connector is not None:
            return connector.accelerator_source_type()

        return "database"

    @staticmethod
    def resolve_connection(params: dict[str, Any]) -> dict[str, Any]:
        connection_id = params.get("connection_id")

        if not connection_id:
            return {
                "databaseType": params.get("databaseType", ""),
                "connectionDetails": params.get("connectionDetails", {}),
            }

        from services.saved_connection_service import saved_connection_service

        resolved = saved_connection_service.get_decrypted_for_run(connection_id)

        if resolved is None:
            logger.warning(
                "Job references saved connection '%s', which no longer exists",
                connection_id,
            )
            return {
                "databaseType": params.get("databaseType", ""),
                "connectionDetails": params.get("connectionDetails", {}),
            }

        return {
            "databaseType": resolved.get("db_type", ""),
            "connectionDetails": resolved.get("connection_details", {}),
        }

    def _build_connection_string(
        self,
        params: dict[str, Any],
    ) -> str:
        connection_string = params.get(
            "connection_string",
            "",
        )

        resolved = self.resolve_connection(params)

        database_type = resolved["databaseType"]
        connection_details = resolved["connectionDetails"]

        if not (database_type and connection_details):
            return connection_string

        try:
            return connection_service.build_connection_string(
                database_type,
                connection_details,
            )
        except Exception as exc:
            logger.warning(
                "Failed to build connection string: %s",
                exc,
            )
            return connection_string

    def _build_tables(
        self,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger.debug(
            "Building tables from pipeline params: %s",
            params.get("tables", []),
        )

        tables: list[dict[str, Any]] = []

        for table in params.get("tables", []):
            if not isinstance(table, dict):
                raise ValueError(
                    f"Malformed source table entry {table!r}: expected an object "
                    f"with a 'name'. Re-select this job's source tables."
                )

            entry = {
                "name": table.get("name", ""),
                "schema": table.get(
                    "schema",
                    "public",
                ),
                "primary_key": [
                    key.strip()
                    for key in table.get(
                        "primary_key",
                        "",
                    ).split(",")
                    if key.strip()
                ],
            }

            tables.append(entry)

        return tables

    def resolve_profile_map_path(
        self,
        job_id: str,
        params: dict[str, Any],
    ) -> Path | None:
        job_dir = get_job_dir(job_id)

        profile_map_file = params.get(
            "profile_map_file",
            "",
        )

        step = str(
            params.get(
                "step",
                "1",
            )
        )

        if step == "1":
            return get_profile_map_job_path(job_id)

        from core.storage_layout import get_profile_map_upload_dir

        profile_map_upload_dir = get_profile_map_upload_dir()

        if profile_map_file:
            uploaded_profile_map = (
                profile_map_upload_dir
                / profile_map_file
            )

            return uploaded_profile_map

        return None

    def _build_staging_configuration(
        self,
        job_id: str,
        run_mode: int,
        connection_string: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        staging_path = str(
            get_staging_dir(job_id)
        ) + "/"

        connector = self._get_connector(params)

        supports_staging = (
            connector.supports_database_staging()
            if connector is not None
            else True
        )

        if (
            run_mode == 2
            and supports_staging
        ):
            resolved = self.resolve_connection(params)
            connection_details = resolved["connectionDetails"]

            staging_connector = (
                self._get_connector(
                    {**params, "databaseType": resolved["databaseType"]}
                )
                or connector
            )

            accelerator_credentials = (
                staging_connector.accelerator_credentials(connection_details)
                if staging_connector is not None
                else {}
            )

            return {
                "type": "database",
                "base_path": staging_path,
                "db": {
                    "connection_string": connection_string,
                    "schema": "staging",
                    "if_exists": "replace",
                    **accelerator_credentials,
                },
            }

        return {
            "type": "csv",
            "base_path": staging_path,
        }


config_builder = ConfigBuilder()
