from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.connectors.salesforce_connector import SalesforceConnector
from common.errors.friendly_errors import describe_connection_error


DETAILS = {
    "username": "user@example.com",
    "password": "secret",
    "security_token": "token123",
    "domain": "login",
}


@pytest.fixture
def connector() -> SalesforceConnector:
    return SalesforceConnector()


def test_accelerator_source_type_is_salesforce(connector):
    assert connector.accelerator_source_type() == "salesforce"


def test_accelerator_credentials_returns_raw_fields(connector):
    assert connector.accelerator_credentials(DETAILS) == DETAILS


def test_accelerator_credentials_defaults_missing_domain(connector):
    details = {"username": "u", "password": "p", "security_token": "t"}
    assert connector.accelerator_credentials(details)["domain"] == "login"


def test_does_not_support_database_staging(connector):
    assert connector.supports_database_staging() is False


def test_does_not_support_sql_metadata_inspection(connector):
    assert connector.supports_sql_metadata_inspection() is False


def test_list_schemas_returns_the_single_logical_schema(connector):
    assert connector.list_schemas(DETAILS) == ["Salesforce"]


@pytest.mark.parametrize(
    "raw_domain, expected",
    [
        ("login", "login"),
        ("login.salesforce.com", "login"),
        ("https://login.salesforce.com", "login"),
        ("http://login.salesforce.com/", "login"),
        ("test.salesforce.com", "test"),
        ("https://test.salesforce.com", "test"),
        ("mycompany.my.salesforce.com", "mycompany.my.salesforce.com"),
    ],
)
def test_create_client_normalizes_domain(raw_domain, expected):
    with patch("services.connectors.salesforce_connector.Salesforce") as mock_salesforce:
        SalesforceConnector.create_client({**DETAILS, "domain": raw_domain})

    kwargs = mock_salesforce.call_args.kwargs

    assert kwargs["username"] == DETAILS["username"]
    assert kwargs["password"] == DETAILS["password"]
    assert kwargs["security_token"] == DETAILS["security_token"]
    assert kwargs["domain"] == expected


def test_create_client_supplies_a_session_with_timeouts():
    with patch("services.connectors.salesforce_connector.Salesforce") as mock_salesforce:
        SalesforceConnector.create_client(DETAILS)

    session = mock_salesforce.call_args.kwargs["session"]

    assert session is not None
    assert getattr(session, "_timeout", None) is not None


def test_list_tables_returns_sorted_object_names_skipping_unnamed():
    fake_client = MagicMock()
    fake_client.describe.return_value = {
        "sobjects": [
            {"name": "Contact"},
            {"name": "Account"},
            {"name": ""},
            {},
        ]
    }

    with patch.object(SalesforceConnector, "create_client", return_value=fake_client):
        result = SalesforceConnector().list_tables(DETAILS, schema="Salesforce")

    assert result == ["Account", "Contact"]


def test_list_columns_returns_sorted_field_names_skipping_unnamed():
    fake_object = MagicMock()
    fake_object.describe.return_value = {
        "fields": [
            {"name": "Name"},
            {"name": "Id"},
            {"name": None},
        ]
    }
    fake_client = MagicMock()
    fake_client.Account = fake_object

    with patch.object(SalesforceConnector, "create_client", return_value=fake_client):
        result = SalesforceConnector().list_columns(DETAILS, schema="Salesforce", table="Account")

    assert result == ["Id", "Name"]


def test_test_succeeds_when_organization_query_returns_a_record():
    fake_client = MagicMock()
    fake_client.query.return_value = {"records": [{"Id": "00Dxx0000000001"}]}

    with patch.object(SalesforceConnector, "create_client", return_value=fake_client):
        result = SalesforceConnector().test(DETAILS)

    assert result == {"ok": True, "message": "SALESFORCE connected successfully ✅"}


def test_test_fails_when_organization_query_returns_no_records():
    fake_client = MagicMock()
    fake_client.query.return_value = {"records": []}

    with patch.object(SalesforceConnector, "create_client", return_value=fake_client):
        result = SalesforceConnector().test(DETAILS)

    assert result["ok"] is False


@pytest.mark.parametrize(
    "raw_error, expected_message",
    [
        (
            "INVALID_LOGIN: Invalid username, password, security token; or user locked out.",
            "Salesforce login failed. Check username, password, and security token.",
        ),
        (
            "INVALID_SECURITY_TOKEN: Invalid security token.",
            "Invalid Salesforce security token. Reset the security token and try again.",
        ),
        (
            "LOGIN_MUST_USE_SECURITY_TOKEN: ...",
            "Salesforce requires a security token for this login.",
        ),
    ],
)
def test_test_translates_salesforce_specific_errors(raw_error, expected_message):
    with patch.object(SalesforceConnector, "create_client", side_effect=Exception(raw_error)):
        result = SalesforceConnector().test(DETAILS)

    assert result == {"ok": False, "error": expected_message}


def test_error_patterns_are_reachable_directly_through_friendly_errors():
    message = describe_connection_error(
        Exception("INVALID_LOGIN: bad creds"),
        SalesforceConnector.error_patterns,
    )
    assert message == "Salesforce login failed. Check username, password, and security token."
