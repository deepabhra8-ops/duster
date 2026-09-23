"""Microsoft SQL Server database connector."""

from __future__ import annotations

from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


@register_connector
class MssqlConnector(DatabaseConnector):
    """Builds SQL Server connection strings."""

    db_type = "mssql"
    required_fields = ("host", "username", "password", "database")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a pyodbc SQLAlchemy connection string."""
        return (
            f"mssql+pyodbc://{details.get('username', '')}:{details.get('password', '')}"
            f"@{details.get('host', '')}:{details.get('port', 1433)}/{details.get('database', '')}"
            f"?driver=ODBC+Driver+18+for+SQL+Server&Encrypt={details.get('encrypt', 'yes')}"
            f"&TrustServerCertificate={details.get('trust_server_certificate', 'no')}"
        )
