from __future__ import annotations

import hashlib
import hmac
import re

from core.config import AUTH_ALLOW_LEGACY_PLAINTEXT
from utils.logger import get_logger


logger = get_logger(__name__)

_TAG_SEPARATOR = "$"
_DEFAULT_ALGORITHM = "sha256"

_BARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_hex(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return f"{_DEFAULT_ALGORITHM}{_TAG_SEPARATOR}{_sha256_hex(password)}"


def classify(stored: str | None) -> str:
    if not stored:
        return "plaintext"

    algorithm, separator, _ = stored.partition(_TAG_SEPARATOR)

    if separator and algorithm in _VERIFIERS:
        return "tagged"

    if _BARE_SHA256_RE.match(stored):
        return "bare_sha256"

    return "plaintext"


def retag_bare_sha256(digest: str) -> str:
    if not _BARE_SHA256_RE.match(digest):
        raise ValueError("Not a bare SHA-256 digest")

    return f"sha256{_TAG_SEPARATOR}{digest}"


def verify_password(submitted: str, stored: str | None) -> tuple[bool, bool]:
    if not submitted or not stored:
        return False, False

    algorithm, separator, digest = stored.partition(_TAG_SEPARATOR)

    if separator:
        verifier = _VERIFIERS.get(algorithm)

        if verifier is None:
            logger.error(
                "Stored credential uses unsupported algorithm '%s'; rejecting",
                algorithm,
            )
            return False, False

        return verifier(submitted, digest), False

    if _BARE_SHA256_RE.match(stored):
        return _verify_sha256(submitted, stored), True

    if not AUTH_ALLOW_LEGACY_PLAINTEXT:
        logger.error(
            "Stored credential is plaintext and AUTH_ALLOW_LEGACY_PLAINTEXT is "
            "off; rejecting. Run migration 006 to hash existing passwords."
        )
        return False, False

    logger.warning(
        "Verified a PLAINTEXT stored password - upgrading it to a hash now. "
        "If this recurs, something is still writing plaintext to the users table."
    )
    return hmac.compare_digest(submitted, stored), True


def _verify_sha256(submitted: str, digest: str) -> bool:
    return hmac.compare_digest(_sha256_hex(submitted), digest)


_VERIFIERS = {
    "sha256": _verify_sha256,
}
