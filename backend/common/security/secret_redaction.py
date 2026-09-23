"""Recursively redacts known-sensitive dict keys before job state is persisted or returned.

Job params (connectionDetails.password, connectionDetails.service_account_json, a raw
connection_string) and the pipeline config built from them (source.db.connection_string,
staging.db.connection_string, ...) both carry live database credentials. Without this,
they flow verbatim into the in-memory job store - and from there straight back out of
GET /api/job/<id> and GET /api/jobs to anyone who can call them, and into the
per-job dq_parameter.yaml written to disk. The real values are still needed once, in
memory, to actually run the pipeline - see PipelineService.run_job, which builds the
config and executes against it before this redaction is ever applied to what gets stored.
"""

from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"

# Matched case-insensitively against dict keys at any depth. Extend this set rather than
# adding redaction logic at individual call sites when a new secret-shaped field appears -
# every connector's secret-bearing field (services/connectors/*.py) must have an entry here,
# since this is the only thing standing between connectionDetails and GET /api/job/<id>.
_SENSITIVE_KEYS = {
    "password",
    "service_account_json",
    "connection_string",
    "access_token",  # DatabricksConnector
    "client_secret",  # AzureSqlConnector (aad_service_principal auth)
}


def redact_secrets(value: Any) -> Any:
    """Return a deep copy of value with sensitive dict keys replaced by a fixed placeholder."""

    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS and val
                else redact_secrets(val)
            )
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [redact_secrets(item) for item in value]

    return value
