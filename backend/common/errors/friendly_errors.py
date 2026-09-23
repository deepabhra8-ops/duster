from __future__ import annotations

import re


_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"password authentication failed"
            r"|access denied for user"
            r"|login failed for user"
            r"|invalid username/password"
            r"|incorrect username or password"
            r"|invalid_grant"
            r"|invalid access token"
            r"|invalid credentials"
            r"|ora-01017"
            r"|ora-01005"
            r"|authentication failed",
            re.IGNORECASE,
        ),
        "Authentication failed. Please verify your username and password (or credentials) and try again.",
    ),
    (
        re.compile(
            r"could not translate host name"
            r"|name or service not known"
            r"|nodename nor servname"
            r"|getaddrinfo failed"
            r"|no such host is known"
            r"|failed to resolve"
            r"|unknown host"
            r"|ora-12545",
            re.IGNORECASE,
        ),
        "Unable to resolve the database host. Please verify the host name and try again.",
    ),
    (
        re.compile(
            r"unknown database"
            r"|database \".*\" does not exist"
            r"|cannot open database"
            r"|no such database"
            r"|ora-12514"
            r"|404 not found"
            r"|not found: dataset",
            re.IGNORECASE,
        ),
        "The specified database/schema was not found. Please verify the database name.",
    ),
    (
        re.compile(
            r"connection refused"
            r"|actively refused"
            r"|is the server running"
            r"|no listener"
            r"|ora-12541"
            r"|ora-12170"
            r"|can't connect to mysql server"
            r"|server closed the connection"
            r"|could not connect to server"
            r"|network-related or instance-specific error"
            r"|sql server does not exist or access denied"
            r"|could not connect to snowflake backend"
            r"|connection timed out"
            r"|timeout expired"
            r"|timed out"
            r"|operation timed out",
            re.IGNORECASE,
        ),
        "Unable to connect, please verify your credentials or check if the database is up and running.",
    ),
    (
        re.compile(
            r"permission denied"
            r"|insufficient privilege"
            r"|the caller does not have permission"
            r"|403 (access denied|forbidden)",
            re.IGNORECASE,
        ),
        "Access denied. Please verify the account has permission to access this database.",
    ),
    (
        re.compile(
            r"certificate verify failed"
            r"|ssl.{0,20}(error|handshake)"
            r"|tls.{0,20}(error|handshake)",
            re.IGNORECASE,
        ),
        "A secure connection could not be established. Please check your SSL/TLS settings and try again.",
    ),
)

_DEFAULT_MESSAGE = (
    "Unable to connect, please verify your credentials or check if the database is up and running."
)

_MISSING_DRIVER_MESSAGE = (
    "A required database driver is missing on the server. Please contact your administrator."
)

_INVALID_CREDENTIALS_FILE_MESSAGE = (
    "The service account credentials file is invalid or malformed. Please check the file and try again."
)


def describe_connection_error(
    exc: BaseException,
    extra_patterns: tuple[tuple[re.Pattern[str], str], ...] = (),
) -> str:
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return _MISSING_DRIVER_MESSAGE

    if isinstance(exc, ValueError) and "json" in type(exc).__module__:
        return _INVALID_CREDENTIALS_FILE_MESSAGE

    text = str(exc)

    for pattern, message in (*extra_patterns, *_PATTERNS):
        if pattern.search(text):
            return message

    return _DEFAULT_MESSAGE
