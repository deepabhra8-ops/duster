from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class RedshiftConnector(DatabaseConnector):
    db_type = "redshift"
    required_fields = ("host", "username", "password", "database")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        ssl_enabled = details.get("ssl_enabled", True)
        ssl = "?sslmode=require" if ssl_enabled is not False else ""

        return (
            f"redshift+psycopg2://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('host', '')}:{details.get('port', 5439)}/{details.get('database', '')}{ssl}"
        )

    def connect_args(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        args = super().connect_args(details)
        ssl_enabled = details.get("ssl_enabled", True)
        if ssl_enabled is not False:
            args["sslmode"] = "require"
        return args
