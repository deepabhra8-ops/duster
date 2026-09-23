from __future__ import annotations

import re

from common.errors.friendly_errors import describe_connection_error


def test_generic_pattern_matches_connection_refused():
    message = describe_connection_error(Exception("Connection refused by remote host"))
    assert "Unable to connect" in message


def test_generic_pattern_matches_authentication_failure():
    message = describe_connection_error(Exception('password authentication failed for user "x"'))
    assert "Authentication failed" in message


def test_unmatched_text_falls_back_to_default_message():
    message = describe_connection_error(Exception("some totally unrecognized driver error"))
    assert message == (
        "Unable to connect, please verify your credentials or check if the database is up and running."
    )


def test_import_error_reports_missing_driver():
    message = describe_connection_error(ImportError("No module named 'psycopg2'"))
    assert "driver is missing" in message


def test_extra_patterns_are_checked_before_generic_patterns():
    extra_patterns = (
        (re.compile(r"custom_marker"), "Custom connector-specific message."),
    )

    message = describe_connection_error(
        Exception("custom_marker: authentication failed"),
        extra_patterns,
    )

    assert message == "Custom connector-specific message."


def test_extra_patterns_fall_through_to_generic_when_they_do_not_match():
    extra_patterns = (
        (re.compile(r"custom_marker"), "Custom connector-specific message."),
    )

    message = describe_connection_error(
        Exception("connection refused"),
        extra_patterns,
    )

    assert "Unable to connect" in message


def test_no_extra_patterns_behaves_exactly_as_before():
    message = describe_connection_error(Exception("connection refused"))
    assert "Unable to connect" in message
