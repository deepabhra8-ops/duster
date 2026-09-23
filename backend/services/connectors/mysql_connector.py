"""MySQL database connector."""

from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class MysqlConnector(DatabaseConnector):
    """Builds MySQL connection strings."""

    db_type = "mysql"
    required_fields = ("host", "username", "password")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a pymysql SQLAlchemy connection string."""
        database = details.get("database", "")
        ssl_enabled = details.get("ssl_enabled", True)
        ssl = "?ssl_mode=REQUIRED" if ssl_enabled is not False else ""

        return (
            f"mysql+pymysql://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('host', '')}:{details.get('port', 3306)}"
            f"{'/' + database if database else ''}"
            f"{ssl}"
        )
