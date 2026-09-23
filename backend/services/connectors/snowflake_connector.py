"""Snowflake database connector."""

from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class SnowflakeConnector(DatabaseConnector):
    """Builds Snowflake connection strings."""

    db_type = "snowflake"
    required_fields = (
        "account",
        "username",
        "password",
        "warehouse",
        "database",
        "schema",
    )

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a Snowflake SQLAlchemy connection string. 'role' is optional and read directly from details."""
        params = [
            f"warehouse={details.get('warehouse', '')}",
            f"role={details.get('role', '')}",
        ]
        params = [param for param in params if not param.endswith("=")]

        return (
            f"snowflake://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('account', '')}/{details.get('database', '')}/{details.get('schema', '')}"
            f"{'?' + '&'.join(params) if params else ''}"
        )
