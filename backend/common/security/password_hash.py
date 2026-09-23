"""Hashing and verification for the `users` table's login passwords.

Separate from common/security/crypto.py on purpose. That module is Fernet *encryption*
for saved database credentials, which must be recoverable in their original
form to connect later; a login password only ever needs to be *verified*, so
it is hashed one-way and never recovered. crypto.py also raises when
CONNECTION_ENCRYPTION_KEY is unset - login must never acquire a dependency on
that key, or a missing connection key would take authentication down with it.

Storage format is algorithm-tagged: `sha256$<64 lowercase hex>`. The tag costs
one string concat and buys two things - a stored value's algorithm is
self-describing rather than guessed, and moving to bcrypt later is a new entry
in _VERIFIERS plus a new hash_password default, with no second data migration
and with both formats coexisting indefinitely.

Known limitation of SHA-256, recorded deliberately: it is a fast, unsalted
hash. A commodity GPU tries billions of candidates per second, and without a
per-user salt, identical passwords produce identical digests, so precomputed
rainbow tables apply. bcrypt/argon2 are slow and salted and defeat both. This
was an explicit product decision for the PoC; the tagged format above is what
keeps the upgrade cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from core.config import AUTH_ALLOW_LEGACY_PLAINTEXT
from utils.logger import get_logger


logger = get_logger(__name__)

_TAG_SEPARATOR = "$"
_DEFAULT_ALGORITHM = "sha256"

# An untagged stored value that looks exactly like a SHA-256 digest is treated
# as one - that is how rows written by the external system (or by a build that
# predates tagging) are recognised. The failure mode is one-directional and
# documented: a user whose real plaintext password happens to be exactly 64
# lowercase hex characters is read as already-hashed and can never log in. That
# is an availability bug for a vanishingly rare password, not a disclosure, and
# it is preferred over the alternative (treating a real digest as plaintext).
_BARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_hex(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Return the tagged hash to store for `password`."""

    return f"{_DEFAULT_ALGORITHM}{_TAG_SEPARATOR}{_sha256_hex(password)}"


def classify(stored: str | None) -> str:
    """Describe a stored credential's format: 'tagged', 'bare_sha256', or 'plaintext'.

    Shared with scripts/rehash_passwords.py so the audit and the verifier can
    never disagree about what a stored value is.
    """

    if not stored:
        return "plaintext"

    algorithm, separator, _ = stored.partition(_TAG_SEPARATOR)

    if separator and algorithm in _VERIFIERS:
        return "tagged"

    if _BARE_SHA256_RE.match(stored):
        return "bare_sha256"

    return "plaintext"


def retag_bare_sha256(digest: str) -> str:
    """Wrap an untagged SHA-256 digest in the current format, without the plaintext."""

    if not _BARE_SHA256_RE.match(digest):
        raise ValueError("Not a bare SHA-256 digest")

    return f"sha256{_TAG_SEPARATOR}{digest}"


def verify_password(submitted: str, stored: str | None) -> tuple[bool, bool]:
    """Check `submitted` against a stored credential.

    Returns (ok, needs_rehash). `needs_rehash` is True when the credential
    verified but is not in the current tagged format, so the caller should
    write hash_password(submitted) back - that is what converts legacy rows on
    first successful login, including any the external system inserts later.
    """

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

    # Untagged. Either a legacy bare SHA-256 digest, or plaintext.
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


# Adding bcrypt later: register it here and change _DEFAULT_ALGORITHM. Existing
# sha256$ rows keep verifying through this table, and each one upgrades itself
# on its owner's next login via the needs_rehash path above.
_VERIFIERS = {
    "sha256": _verify_sha256,
}
