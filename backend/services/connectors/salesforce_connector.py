from __future__ import annotations

import re
from typing import Any

from simple_salesforce import Salesforce

from services.connectors.base_connector import DatabaseConnector
from services.connectors.registry import register_connector
from common.errors.friendly_errors import describe_connection_error
from utils.logger import get_logger
from common.salesforce_session import build_salesforce_session


logger = get_logger(__name__)

_COMPOUND_FIELD_TYPES = frozenset({"address", "location"})


@register_connector
class SalesforceConnector(DatabaseConnector):
    db_type = "salesforce"
    required_fields = ("username", "password", "security_token", "domain")

    error_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"invalid_security_token", re.IGNORECASE),
            "Invalid Salesforce security token. Reset the security token and try again.",
        ),
        (
            re.compile(r"login_must_use_security_token", re.IGNORECASE),
            "Salesforce requires a security token for this login.",
        ),
        (
            re.compile(r"invalid_login", re.IGNORECASE),
            "Salesforce login failed. Check username, password, and security token.",
        ),
    )

    def build_connection_string(
        self,
        details: dict[str, Any],
    ) -> str:
        return "salesforce://simple-salesforce"

    def test(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            sf = self.create_client(details)
            identity = sf.query("SELECT Id FROM Organization LIMIT 1")

            if not identity.get("records"):
                raise RuntimeError(
                    "Salesforce authentication succeeded but Organization could not be queried."
                )

            logger.info(
                "Salesforce connection test succeeded for user '%s'",
                details.get("username"),
            )
            return {
                "ok": True,
                "message": "SALESFORCE connected successfully ✅",
            }

        except Exception as exc:
            logger.warning(
                "Salesforce connection test failed: %s",
                exc,
            )
            return {
                "ok": False,
                "error": describe_connection_error(exc, self.error_patterns),
            }

    def accelerator_source_type(self) -> str:
        return "salesforce"

    def accelerator_credentials(self, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "username": details.get("username", ""),
            "password": details.get("password", ""),
            "security_token": details.get("security_token", ""),
            "domain": details.get("domain", "login"),
        }

    def supports_database_staging(self) -> bool:
        return False

    def supports_sql_metadata_inspection(self) -> bool:
        return False

    def list_schemas(self, details: dict[str, Any]) -> list[str]:
        return ["Salesforce"]

    def list_tables(self, details: dict[str, Any], schema: str) -> list[str]:
        return self.get_objects(details)

    def list_columns(self, details: dict[str, Any], schema: str, table: str) -> list[str]:
        return self.get_fields(details, table)

    @staticmethod
    def create_client(details: dict[str, Any]) -> Salesforce:
        domain = str(details.get("domain", "login")).strip()
        domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

        if domain == "login.salesforce.com":
            domain = "login"
        elif domain == "test.salesforce.com":
            domain = "test"

        return Salesforce(
            username=details["username"],
            password=details["password"],
            security_token=details["security_token"],
            domain=domain,
            session=build_salesforce_session(),
        )

    @classmethod
    def get_objects(cls, details: dict[str, Any]) -> list[str]:
        sf = cls.create_client(details)

        return sorted(
            obj["name"]
            for obj in sf.describe().get("sobjects", [])
            if obj.get("name")
        )

    @classmethod
    def get_fields(cls, details: dict[str, Any], object_name: str) -> list[str]:
        sf = cls.create_client(details)
        describe = getattr(sf, object_name).describe()

        return sorted(
            field["name"]
            for field in describe.get("fields", [])
            if field.get("name")
            and str(field.get("type", "")).strip().lower() not in _COMPOUND_FIELD_TYPES
        )
