from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.config import CONNECTION_ENCRYPTION_KEY


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
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
    token = _get_fernet().encrypt(json.dumps(data).encode())
    return token.decode()


def decrypt_json(token: str) -> dict[str, Any]:
    try:
        raw = _get_fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise ValueError(
            "Stored connection details could not be decrypted - wrong or rotated "
            "CONNECTION_ENCRYPTION_KEY?"
        ) from exc

    return json.loads(raw.decode())
