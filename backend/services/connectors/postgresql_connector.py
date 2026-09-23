"""PostgreSQL database connector."""

from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class PostgresqlConnector(DatabaseConnector):
    """Builds PostgreSQL connection strings."""

    db_type = "postgresql"
    required_fields = ("host", "username", "password")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a psycopg2 SQLAlchemy connection string."""
        database = details.get("database", "")

        return (
            f"postgresql+psycopg2://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('host', '')}:{details.get('port', 5432)}"
            f"{'/' + database if database else ''}"
            f"?sslmode={details.get('ssl_mode', 'require')}"
        )
