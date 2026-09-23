"""Symmetric encryption for data that must be recoverable in its original form.

Used for saved database connections' credentials (see
repositories/saved_connection_repository.py) - real passwords for external
databases, which must be readable back (not just verifiable, unlike a login
password) in order to actually connect later. That is why this is Fernet
encryption rather than hashing.

Note this is unrelated to, and must not be taken as a model for, the `users`
table's password_hash column, which currently holds plaintext (see
auth_service.login) - that is a known defect tracked separately, not a design
choice to imitate here.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.config import CONNECTION_ENCRYPTION_KEY


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Return the process-wide Fernet instance, built lazily from CONNECTION_ENCRYPTION_KEY.

    Lazy (not built at import time) so the backend can still start - and serve
    every route that doesn't touch saved connections - even before this key is
    configured; only an actual save/list/decrypt call needs it.
    """

    global _fernet

    if _fernet is not None:
        return _fernet

    if not CONNECTION_ENCRYPTION_KEY:
        raise RuntimeError(
            "CONNECTION_ENCRYPTION_KEY is not configured. Set it in backend/.env "
            "(see backend/.env.example) - generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )

    try:
        _fernet = Fernet(CONNECTION_ENCRYPTION_KEY.encode())
    except Exception as exc:
        raise RuntimeError(
            f"CONNECTION_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
        ) from exc

    return _fernet


def encrypt_json(data: dict[str, Any]) -> str:
    """Encrypt a JSON-serializable dict to an opaque, storable string."""

    token = _get_fernet().encrypt(json.dumps(data).encode())
    return token.decode()


def decrypt_json(token: str) -> dict[str, Any]:
    """Decrypt a string produced by encrypt_json() back to its original dict."""

    try:
        raw = _get_fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise ValueError(
            "Stored connection details could not be decrypted - wrong or rotated "
            "CONNECTION_ENCRYPTION_KEY?"
        ) from exc

    return json.loads(raw.decode())
