from typing import Any

from core.config import DEFAULT_DATABASE_CONNECT_TIMEOUT
from services.connectors import connector_registry
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger


logger = get_logger(__name__)


class ConnectionService:
    def build_connection_string(
        self,
        db_type: str,
        details: dict[str, Any],
    ) -> str:
        connector = connector_registry.get(db_type)

        if connector is None:
            raise ValueError(f"Unsupported database type: {db_type}")

        return connector.build_connection_string(details)

    def resolve_connection_string(
        self,
        params: dict[str, Any],
    ) -> str:
        database_type = params.get("databaseType", "")
        connection_details = params.get("connectionDetails", {})

        if database_type and connection_details:
            return self.build_connection_string(
                database_type,
                connection_details,
            )

        connection_string = params.get("connection_string", "")

        if connection_string:
            return connection_string

        raise ValueError("Database connection information not available")

    def validate_connection_details(
        self,
        db_type: str,
        details: dict[str, Any],
    ) -> list[str]:
        connector = connector_registry.get(db_type)

        if connector is None:
            return []

        return connector.validate(details)

    def test_connection_string(
        self,
        connection_string: str,
    ) -> dict[str, Any]:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(
                connection_string,
                connect_args={
                    "connect_timeout": DEFAULT_DATABASE_CONNECT_TIMEOUT
                },
            )

            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            return {
                "ok": True,
                "message": "Connected successfully ✅",
            }

        except Exception as exc:
            logger.warning("Legacy database connection test failed: %s", exc)
            return {
                "ok": False,
                "error": describe_connection_error(exc),
            }

    def test_connection(
        self,
        db_type: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        if not db_type:
            return {
                "ok": False,
                "error": "databaseType is required",
            }

        connector = connector_registry.get(db_type)

        if connector is None:
            return {
                "ok": False,
                "error": f"Unsupported database type: {db_type}",
            }

        missing = connector.validate(details)

        if missing:
            return {
                "ok": False,
                "error": (
                    "Missing required fields: "
                    + ", ".join(missing)
                ),
            }

        return connector.test(details)


connection_service = ConnectionService()
