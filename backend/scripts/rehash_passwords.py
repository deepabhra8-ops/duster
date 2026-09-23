"""One-off: report and upgrade stored password formats in the users table.

Usage, from the backend/ directory:

    python scripts/rehash_passwords.py --status   # count each format, change nothing
    python scripts/rehash_passwords.py --retag    # bare digest -> sha256$<digest>

Deliberately NOT a numbered SQL migration. The `users` table is externally
managed and lives in a schema named by USERS_TABLE_SCHEMA, which a static .sql
file cannot read; more importantly, migrations can run automatically on
container boot (RUN_MIGRATIONS_ON_START), and silently rewriting another
system's table on deploy is not something that should happen without an
operator deciding to. Doing it here also means the hashing is literally
common.security.password_hash.hash_password, so a backfill can never disagree with the
verifier about the stored format.

Note what this can and cannot do. Re-tagging a bare digest needs no plaintext
and is done by --retag. Converting a PLAINTEXT row to a hash is not done here:
that would require reading every plaintext password into this process, and it
is unnecessary - auth_service upgrades each plaintext row automatically on its
owner's next successful login. Run --status to watch that number fall.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Allow running this file directly from backend/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.user_repository import user_repository  # noqa: E402
from common.security.password_hash import classify, retag_bare_sha256  # noqa: E402


def print_status(credentials: list[tuple[str, str]]) -> None:
    counts = Counter(classify(stored) for _, stored in credentials)

    print(f"{len(credentials)} account(s):")
    print(f"  tagged (sha256$...) : {counts['tagged']}")
    print(f"  bare sha256 digest  : {counts['bare_sha256']}  (run --retag)")
    print(f"  plaintext           : {counts['plaintext']}  (upgraded on next login)")

    if counts["plaintext"]:
        print(
            "\nPlaintext rows are a live exposure until their owners next sign in. "
            "Reset them with scripts/create_user.py if that wait is unacceptable."
        )


def retag(credentials: list[tuple[str, str]]) -> int:
    """Rewrite bare digests in the tagged format. Returns the number changed."""

    changed = 0

    for username, stored in credentials:
        if classify(stored) != "bare_sha256":
            continue

        if user_repository.set_password_hash(username, retag_bare_sha256(stored)):
            changed += 1

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Report formats, change nothing")
    group.add_argument("--retag", action="store_true", help="Tag bare digests as sha256$<digest>")
    args = parser.parse_args()

    credentials = user_repository.list_stored_credentials()

    if args.status:
        print_status(credentials)
        return

    changed = retag(credentials)
    print(f"Re-tagged {changed} account(s).")
    print_status(user_repository.list_stored_credentials())


if __name__ == "__main__":
    main()
