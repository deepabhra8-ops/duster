"""Google BigQuery database connector."""

from __future__ import annotations

import json
from typing import Any

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger


logger = get_logger(__name__)


@register_connector
class BigqueryConnector(DatabaseConnector):
    """Builds and tests BigQuery connections using service-account credentials."""

    db_type = "bigquery"
    required_fields = ("project_id", "dataset_id")

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        """Build a BigQuery SQLAlchemy connection string."""
        return f"bigquery://{details.get('project_id', '')}/{details.get('dataset_id', '')}"

    def validate(
        self,
        details: dict[str, Any],
    ) -> list[str]:
        """Return missing required fields, including service_account_json."""
        missing = super().validate(details)

        if not str(details.get("service_account_json", "")).strip():
            missing.append("service_account_json")

        return missing

    def accelerator_credentials(self, details: dict[str, Any]) -> dict[str, Any]:
        """Return the service-account credentials the engine's dedicated BigQuery read/write
        path needs directly - it doesn't go through JDBC, so a connection_string alone
        (built above) isn't enough."""
        return {
            "service_account_json": details.get("service_account_json", ""),
            "project_id": details.get("project_id", ""),
            "dataset_id": details.get("dataset_id", ""),
        }

    def test(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Test a BigQuery connection using service-account credentials, bypassing SQLAlchemy entirely."""

        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            service_account_json = details.get("service_account_json", "")

            if not service_account_json.strip().startswith("{"):
                return {
                    "ok": False,
                    "error": (
                        "The service account credentials must be a valid JSON object. "
                        "Please check the file and try again."
                    ),
                }

            credentials_info = json.loads(service_account_json)

            credentials = service_account.Credentials.from_service_account_info(
                credentials_info
            )

            client = bigquery.Client(
                project=details.get("project_id"),
                credentials=credentials,
            )

            list(client.list_datasets(max_results=1))

            logger.info("Database connection test succeeded for type 'bigquery'")
            return {
                "ok": True,
                "message": "BigQuery connected successfully ✅",
            }

        except Exception as exc:
            logger.warning("Database connection test failed for type 'bigquery': %s", exc)
            return {
                "ok": False,
                "error": describe_connection_error(exc),
            }
