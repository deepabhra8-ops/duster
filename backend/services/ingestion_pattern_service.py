from __future__ import annotations

from typing import Any

from repositories.ingestion_config_repository import ingestion_config_repository
from services.saved_connection_service import saved_connection_service


SYSTEM_TYPE_BY_DB_TYPE = {
    "snowflake": "warehouse",
    "bigquery": "warehouse",
    "redshift": "warehouse",
    "databricks": "warehouse",
    "postgresql": "database",
    "mysql": "database",
    "mssql": "database",
    "oracle": "database",
    "azure_sql": "database",
    "salesforce": "saas",
}

DEFAULT_SYSTEM_TYPE = "database"

MODE_BY_SYSTEM_TYPE = {
    "event_stream": "push",
    "lake": "poll",
}

DEFAULT_MODE = "pull"

VALID_LATENCY_REQUIREMENTS = ("real_time", "hourly", "daily")
VALID_SCHEDULING_OWNERSHIPS = ("saas", "customer")


def classify_system_type(db_type: str) -> str:
    return SYSTEM_TYPE_BY_DB_TYPE.get(str(db_type or "").strip().lower(), DEFAULT_SYSTEM_TYPE)


def decide_mode(system_type: str, latency_requirement: str) -> str:
    return MODE_BY_SYSTEM_TYPE.get(system_type, DEFAULT_MODE)


class IngestionPatternService:
    def preview(self, connection_id: str) -> dict[str, Any] | None:
        connection = saved_connection_service.get(connection_id)

        if connection is None:
            return None

        system_type = classify_system_type(connection["db_type"])
        config = ingestion_config_repository.get(connection_id)

        return {
            "connectionName": connection["name"],
            "dbType": connection["db_type"],
            "systemType": system_type,
            "config": config,
        }

    def save(
        self,
        connection_id: str,
        username: str,
        latency_requirement: str,
        scheduling_ownership: str,
    ) -> dict[str, Any] | None:
        if latency_requirement not in VALID_LATENCY_REQUIREMENTS:
            raise ValueError(
                f"latencyRequirement must be one of {', '.join(VALID_LATENCY_REQUIREMENTS)}"
            )

        if scheduling_ownership not in VALID_SCHEDULING_OWNERSHIPS:
            raise ValueError(
                f"schedulingOwnership must be one of {', '.join(VALID_SCHEDULING_OWNERSHIPS)}"
            )

        connection = saved_connection_service.get_for_edit(connection_id, username)

        if connection is None:
            return None

        system_type = classify_system_type(connection["db_type"])
        mode = decide_mode(system_type, latency_requirement)

        return ingestion_config_repository.upsert(
            connection_id=connection_id,
            system_type=system_type,
            latency_requirement=latency_requirement,
            scheduling_ownership=scheduling_ownership,
            ingestion_mode=mode,
        )


ingestion_pattern_service = IngestionPatternService()
