from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class OracleConnector(DatabaseConnector):
    db_type = "oracle"
    required_fields = ("host", "username", "password")

    def validate(
        self,
        details: dict[str, Any],
    ) -> list[str]:
        required = list(self.required_fields)
        required.append(
            "sid"
            if details.get("connection_mode", "service_name") == "sid"
            else "service_name"
        )

        return [
            field
            for field in required
            if not str(details.get(field, "")).strip()
        ]

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        key = (
            "sid"
            if details.get("connection_mode", "service_name") == "sid"
            else "service_name"
        )

        value = details.get(key, "")

        return (
            f"oracle+oracledb://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('host', '')}:{details.get('port', 1521)}"
            f"/?{key}={value}"
        )
