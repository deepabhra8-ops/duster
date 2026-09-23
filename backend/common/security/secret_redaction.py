from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "password",
    "service_account_json",
    "connection_string",
    "access_token",
    "client_secret",
}


def redact_secrets(value: Any) -> Any:
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
