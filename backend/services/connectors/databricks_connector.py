"""Databricks SQL warehouse database connector."""

from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class DatabricksConnector(DatabaseConnector):
    """Builds Databricks connection strings."""

    db_type = "databricks"
    required_fields = ("server_hostname", "access_token", "http_path")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a Databricks SQLAlchemy connection string."""
        params = [f"http_path={details.get('http_path', '')}"]
        params += [
            f"{key}={details[key]}"
            for key in ("catalog", "schema")
            if details.get(key)
        ]

        return (
            f"databricks://token:{details.get('access_token', '')}"
            f"@{details.get('server_hostname', '')}?{'&'.join(params)}"
        )

    def connect_args(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Return no connect_args - the Databricks dialect does not accept connect_timeout."""
        return {}
