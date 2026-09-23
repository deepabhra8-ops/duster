"""Salesforce connector using simple-salesforce (not a SQLAlchemy/JDBC database)."""

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

# Mirrors engine/data_sources/salesforce_data_source.py's _COMPOUND_FIELD_TYPES. Compound
# fields (Address, Geolocation) are a read-only aggregate view over sibling flat fields that
# already exist as independent fields in describe() (BillingAddress -> BillingStreet,
# BillingCity, ...) - SOQL has no dot-notation into them, so they aren't queryable in
# isolation and are excluded here so the Configure page's column picker (get_fields() below,
# used for e.g. "Primary Key Column") only offers columns SalesforceDataSource can actually
# read. Duplicated rather than imported for the same reason create_client() is duplicated on
# the engine side: engine/ must stay independently deployable to AWS Glue without this
# services package.
_COMPOUND_FIELD_TYPES = frozenset({"address", "location"})


@register_connector
class SalesforceConnector(DatabaseConnector):
    """Connects to Salesforce via simple-salesforce.

    Also the single place Salesforce client creation and object/field metadata lookups
    live - SalesforceDataSource (bulk reads) and metadata_routes.py (the Configure page's
    schema/object/field browser) both use these, since Salesforce has no SQLAlchemy dialect
    for either of them to fall back to the generic engine/inspector-based paths every other
    connector uses. That's also why this connector overrides more DatabaseConnector hooks
    than most (accelerator_source_type, accelerator_credentials,
    supports_database_staging, supports_sql_metadata_inspection, list_schemas/tables/columns)
    - each one is the point where the rest of the app would otherwise have needed a
    'salesforce' special case of its own.
    """

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
        """Salesforce has no SQLAlchemy connection string; authentication goes through
        create_client() instead. This return value is a placeholder satisfying the
        DatabaseConnector contract."""
        return "salesforce://simple-salesforce"

    def test(
        self,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Test Salesforce authentication (overrides the SQLAlchemy-based default test())."""
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
        """Salesforce is read through SalesforceDataSource, not the generic JDBC-based one."""
        return "salesforce"

    def accelerator_credentials(self, details: dict[str, Any]) -> dict[str, Any]:
        """Return the raw credentials SalesforceDataSource authenticates with directly
        (there's no connection_string for it to parse those back out of)."""
        return {
            "username": details.get("username", ""),
            "password": details.get("password", ""),
            "security_token": details.get("security_token", ""),
            "domain": details.get("domain", "login"),
        }

    def supports_database_staging(self) -> bool:
        """Salesforce isn't a valid JDBC staging target; curation mode falls back to CSV."""
        return False

    def supports_sql_metadata_inspection(self) -> bool:
        """No SQLAlchemy dialect exists for Salesforce, so the generic inspect()-based
        schema/table/column browser can't be used - list_schemas/tables/columns below
        are used instead."""
        return False

    def list_schemas(self, details: dict[str, Any]) -> list[str]:
        """Salesforce has one logical "schema" - there's nothing else to browse to first."""
        return ["Salesforce"]

    def list_tables(self, details: dict[str, Any], schema: str) -> list[str]:
        """Return every Salesforce object (sObject) name available to this connection."""
        return self.get_objects(details)

    def list_columns(self, details: dict[str, Any], schema: str, table: str) -> list[str]:
        """Return a Salesforce object's field names."""
        return self.get_fields(details, table)

    @staticmethod
    def create_client(details: dict[str, Any]) -> Salesforce:
        """Create an authenticated simple-salesforce client.

        Accepts a domain given as "login", "login.salesforce.com", or
        "https://login.salesforce.com" (and the "test" sandbox equivalents).
        """
        domain = str(details.get("domain", "login")).strip()
        domain = domain.replace("https://", "").replace("http://", "").rstrip("/")

        if domain == "login.salesforce.com":
            domain = "login"
        elif domain == "test.salesforce.com":
            domain = "test"

        # The session carries the request timeouts and bounded retries;
        # simple_salesforce's default session has neither, so a hung Salesforce
        # endpoint would tie up a Uvicorn worker indefinitely. Shared with the
        # engine's own client (utils/ ships in the Glue wheel too).
        return Salesforce(
            username=details["username"],
            password=details["password"],
            security_token=details["security_token"],
            domain=domain,
            session=build_salesforce_session(),
        )

    @classmethod
    def get_objects(cls, details: dict[str, Any]) -> list[str]:
        """Return every Salesforce object (sObject) name available to this connection."""
        sf = cls.create_client(details)

        return sorted(
            obj["name"]
            for obj in sf.describe().get("sobjects", [])
            if obj.get("name")
        )

    @classmethod
    def get_fields(cls, details: dict[str, Any], object_name: str) -> list[str]:
        """Return a Salesforce object's queryable field names, excluding compound aggregate
        fields (Address, Geolocation) - see _COMPOUND_FIELD_TYPES. Their data is already
        covered by sibling flat fields, which are already listed separately here."""
        sf = cls.create_client(details)
        describe = getattr(sf, object_name).describe()

        return sorted(
            field["name"]
            for field in describe.get("fields", [])
            if field.get("name")
            and str(field.get("type", "")).strip().lower() not in _COMPOUND_FIELD_TYPES
        )
