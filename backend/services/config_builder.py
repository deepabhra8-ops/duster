"""Builds the complete DQ pipeline configuration dictionary for a job from job parameters, source, LOV, staging, and report settings."""

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
    DEFAULT_SOURCE_TYPE,
    RULES_MASTER_PATH,
)
from services.connection_service import connection_service
from services.connectors import connector_registry
from services.lov_service import lov_service
from utils.logger import get_logger


logger = get_logger(__name__)


class ConfigBuilder:
    """Builds DQ pipeline configuration for a job."""

    def build(
        self,
        job_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the complete DQ pipeline configuration."""

        job_dir = ensure_job_directory(job_id)

        source_type = params.get(
            "source_type",
            DEFAULT_SOURCE_TYPE,
        )

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

        data_dir = self._get_data_directory(params)

        connection_string = self._build_connection_string(
            source_type,
            params,
        )

        tables = self._build_tables(
            source_type,
            params,
        )

        profile_map_path = self.resolve_profile_map_path(
            job_id,
            params,
        )

        # The single LOV this job was created with, if any. LOV uploads land in
        # a shared area, so the job names its own file rather than the run
        # sweeping up every list anyone has ever uploaded.
        lov_file = str(params.get("lov_file", "") or "")

        lov_configuration = (
            lov_service.build_lov_configuration(
                profile_map_path,
                lov_file=lov_file or None,
            )
        )

        staging_configuration = self._build_staging_configuration(
            job_id,
            source_type,
            run_mode,
            connection_string,
            params,
        )

        accelerator_source_type = self._resolve_accelerator_source_type(
            source_type,
            params,
        )

        configuration = {
            "job_id": job_id,
            "project_name": project,
            "run_mode": run_mode,
            "source": {
                "type": accelerator_source_type,
                "base_path": (
                    data_dir.as_posix()
                    if accelerator_source_type == "csv"
                    else ""
                ),
                "chunk_size": int(
                    params.get(
                        "chunk_size",
                        DEFAULT_CHUNK_SIZE,
                    )
                ),
                "tables": tables,
            },
            "staging": staging_configuration,
            "rules_master_file": RULES_MASTER_PATH.as_posix(),
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
            # Read by the Glue run, which resolves the file straight from S3;
            # empty means this job has no LOV and its DQ8 rules will report as
            # not run, which is the honest outcome.
            "lov_file": lov_file,
        }

        if source_type == "database":
            resolved = self.resolve_connection(params)

            source_db = {
                "connection_string": connection_string,
                **self._accelerator_credentials(
                    {**params, "databaseType": resolved["databaseType"]},
                    resolved["connectionDetails"],
                ),
            }

            configuration["source"]["db"] = source_db

        # A validator job sourced from a Profile Mapper job reads that job's stored
        # rows - including the analyst's edits - instead of a workbook. The Glue run
        # loads them by id rather than having them inlined here, which keeps the
        # YAML (and its redacted local audit copy) small and readable.
        source_job_id = params.get("profile_map_source_job_id")

        if source_job_id:
            configuration["profile_map_source_job_id"] = source_job_id

        return configuration

    def _get_connector(
        self,
        params: dict[str, Any],
    ):
        """Return the registered connector for this job's databaseType, or None if there
        isn't one (unconfigured/unknown type - callers fall back to generic behavior)."""
        database_type = str(
            params.get("databaseType", "")
        ).strip().lower()

        return connector_registry.get(database_type)

    def _accelerator_credentials(
        self,
        params: dict[str, Any],
        connection_details: dict[str, Any],
    ) -> dict[str, Any]:
        """Return whatever extra fields this job's connector says its accelerator data
        source needs directly, beyond connection_string (e.g. BigQuery's
        service_account_json, Salesforce's username/password/security_token/domain)."""
        connector = self._get_connector(params)

        if connector is None:
            return {}

        return connector.accelerator_credentials(connection_details)

    def _resolve_accelerator_source_type(
        self,
        source_type: str,
        params: dict[str, Any],
    ) -> str:
        """Resolve the accelerator's data-source implementation name for this source type.

        Most database connectors are read through the generic JDBC-based DatabaseDataSource
        ("database"); a connector overrides accelerator_source_type() when it needs its own
        (e.g. Salesforce → SalesforceDataSource, since it has no JDBC driver at all).
        """
        if source_type in ("csv", "flat_file"):
            return "csv"

        if source_type == "database":
            connector = self._get_connector(params)

            if connector is not None:
                return connector.accelerator_source_type()

        return source_type

    def _get_data_directory(
        self,
        params: dict[str, Any],
    ) -> Path:
        """Return the configured data upload directory."""

        from core.storage_layout import get_data_upload_dir

        data_dir = get_data_upload_dir()
        data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        return data_dir

    @staticmethod
    def resolve_connection(params: dict[str, Any]) -> dict[str, Any]:
        """Return (databaseType, connectionDetails) for a job, resolving a saved connection.

        When the job references a saved connection, credentials are decrypted here
        rather than travelling from the browser - the job's stored params keep only
        the connection_id, so credentials no longer sit in plaintext in jobs.params.
        Falls back to whatever the request supplied directly for the ad-hoc path.
        """
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
        source_type: str,
        params: dict[str, Any],
    ) -> str:
        """Build the connection string when the source is a database."""

        connection_string = params.get(
            "connection_string",
            "",
        )

        if source_type != "database":
            return connection_string

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
        source_type: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build source table configuration entries."""

        logger.debug(
            "Building tables from pipeline params: %s",
            params.get("tables", []),
        )

        tables: list[dict[str, Any]] = []

        for table in params.get("tables", []):
            # A bare string here (which the Validator's upload flow used to store)
            # would raise AttributeError on the .get() calls below, deep inside
            # config building, and surface as an opaque failed Glue job. The routes
            # reject this shape now; this is the backstop for anything already
            # persisted, and it says what is actually wrong.
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

            if source_type in (
                "csv",
                "flat_file",
            ):
                entry["file"] = table.get(
                    "file",
                    "",
                )

            tables.append(entry)

        return tables

    def resolve_profile_map_path(
        self,
        job_id: str,
        params: dict[str, Any],
    ) -> Path | None:
        """Resolve the profile map (rulebook) path for the current pipeline step.

        Public so callers (e.g. the /api/run pre-flight check) can validate a
        Step 3 rulebook actually exists before a job is created, using the same
        resolution order execution will use - rather than discovering a missing
        file only after the job is already marked "running".
        """

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

            # Preserve the filename even if it doesn't exist locally, so Glue can pull it from S3
            return uploaded_profile_map

        return None

    def _build_staging_configuration(
        self,
        job_id: str,
        source_type: str,
        run_mode: int,
        connection_string: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the staging configuration: database staging for curation runs against a database source, CSV otherwise."""

        staging_path = str(
            get_staging_dir(job_id)
        ) + "/"

        connector = self._get_connector(params)

        # A connector opts out via supports_database_staging() (e.g. Salesforce has no real
        # connection_string - see _build_connection_string - and isn't a valid staging
        # destination), in which case curation-mode staging falls back to CSV. No connector
        # resolved at all (e.g. a legacy raw connection_string with no databaseType) is
        # treated as "unknown, assume staging is supported" - the pre-registry default.
        supports_staging = (
            connector.supports_database_staging()
            if connector is not None
            else True
        )

        if (
            run_mode == 2
            and source_type == "database"
            and supports_staging
        ):
            # Resolved rather than read straight off params: a job created against
            # a saved connection stores only connection_id, so reading
            # params["connectionDetails"] here yielded {} and silently dropped the
            # connector-specific staging credentials (BigQuery's service account
            # JSON, for one) that connection_string alone does not carry.
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
