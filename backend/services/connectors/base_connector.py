from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from core.config import DEFAULT_DATABASE_CONNECT_TIMEOUT
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger


logger = get_logger(__name__)


class DatabaseConnector(ABC):
    db_type: str = ""
    required_fields: tuple[str, ...] = ()

    error_patterns: tuple[tuple[re.Pattern[str], str], ...] = ()

    @abstractmethod
    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement "
            "build_connection_string()."
        )

    def validate(
        self,
        details: dict[str, Any],
    ) -> list[str]:
        return [
            field
            for field in self.required_fields
            if not str(details.get(field, "")).strip()
        ]

    def connect_args(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "connect_timeout": DEFAULT_DATABASE_CONNECT_TIMEOUT,
        }

    def test(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(
                self.build_connection_string(details),
                connect_args=self.connect_args(details),
            )

            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            logger.info(
                "Database connection test succeeded for type '%s'",
                self.db_type,
            )
            return {
                "ok": True,
                "message": f"{self.db_type.upper()} connected successfully ✅",
            }

        except Exception as exc:
            logger.warning(
                "Database connection test failed for type '%s': %s",
                self.db_type,
                exc,
            )
            return {
                "ok": False,
                "error": describe_connection_error(exc, self.error_patterns),
            }

    def accelerator_source_type(self) -> str:
        return "database"

    def accelerator_credentials(self, details: dict[str, Any]) -> dict[str, Any]:
        return {}

    def supports_database_staging(self) -> bool:
        return True

    def supports_sql_metadata_inspection(self) -> bool:
        return True

    def list_schemas(self, details: dict[str, Any]) -> list[str]:
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_schemas()."
        )

    def list_tables(self, details: dict[str, Any], schema: str) -> list[str]:
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_tables()."
        )

    def list_columns(self, details: dict[str, Any], schema: str, table: str) -> list[str]:
        raise NotImplementedError(
            f"Connector '{type(self).__name__}' does not implement list_columns()."
        )
