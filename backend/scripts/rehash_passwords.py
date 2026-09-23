from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.user_repository import user_repository
from common.security.password_hash import classify, retag_bare_sha256


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
    changed = 0

    for username, stored in credentials:
        if classify(stored) != "bare_sha256":
            continue

        if user_repository.set_password_hash(username, retag_bare_sha256(stored)):
            changed += 1

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Report and upgrade stored password formats in the users table.")
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
