"""Azure SQL Database connector, supporting SQL login and Microsoft Entra ID (Azure AD) authentication modes."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector


SQL_AUTH = "sql"
AAD_PASSWORD = "aad_password"
AAD_SERVICE_PRINCIPAL = "aad_service_principal"
AAD_DEFAULT = "aad_default"

_AUTH_MODES = (SQL_AUTH, AAD_PASSWORD, AAD_SERVICE_PRINCIPAL, AAD_DEFAULT)


@register_connector
class AzureSqlConnector(DatabaseConnector):
    """Builds Azure SQL connection strings for SQL-login and Entra ID authentication modes."""

    db_type = "azure_sql"

    def _auth_mode(
        self,
        details: dict[str, Any],
    ) -> str:
        """Return the requested authentication mode, defaulting to SQL login."""
        mode = str(details.get("authentication", SQL_AUTH)).strip().lower()
        return mode if mode in _AUTH_MODES else SQL_AUTH

    def validate(
        self,
        details: dict[str, Any],
    ) -> list[str]:
        """Return missing required fields for the selected authentication mode."""
        mode = self._auth_mode(details)
        required = ["host", "database"]

        if mode in (SQL_AUTH, AAD_PASSWORD):
            required += ["username", "password"]
        elif mode == AAD_SERVICE_PRINCIPAL:
            required += ["client_id", "client_secret", "tenant_id"]

        return [
            field
            for field in required
            if not str(details.get(field, "")).strip()
        ]

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a pyodbc SQLAlchemy connection string for the selected authentication mode."""
        mode = self._auth_mode(details)
        host = details.get("host", "")
        port = details.get("port", 1433)
        database = details.get("database", "")

        odbc_params = [
            "driver=ODBC+Driver+18+for+SQL+Server",
            f"Encrypt={details.get('encrypt', 'yes')}",
            f"TrustServerCertificate={details.get('trust_server_certificate', 'no')}",
        ]

        if mode == AAD_PASSWORD:
            odbc_params.append("Authentication=ActiveDirectoryPassword")
            username = quote(str(details.get("username", "")), safe="")
            password = quote(str(details.get("password", "")), safe="")
            userinfo = f"{username}:{password}"

        elif mode == AAD_SERVICE_PRINCIPAL:
            odbc_params.append("Authentication=ActiveDirectoryServicePrincipal")
            client_id = quote(str(details.get("client_id", "")), safe="")
            tenant_id = quote(str(details.get("tenant_id", "")), safe="")
            client_secret = quote(str(details.get("client_secret", "")), safe="")
            userinfo = f"{client_id}@{tenant_id}:{client_secret}"

        elif mode == AAD_DEFAULT:
            odbc_params.append("Authentication=ActiveDirectoryDefault")
            userinfo = ""

        else:
            userinfo = f"{details.get('username', '')}:{details.get('password', '')}"

        return (
            f"mssql+pyodbc://{userinfo}@{host}:{port}/{database}"
            f"?{'&'.join(odbc_params)}"
        )
