"""CLI to reset the password of an existing login account in the users table.

Usage (run from the backend/ directory, with backend/.env configured):
    python scripts/create_user.py <username>

Prompts for the new password (hidden input) so it never lands in shell
history. The value typed here is hashed before it is stored - the hashing
happens inside user_repository.set_password (see common/security/password_hash.py),
so this script never handles the stored form itself.

This only UPDATES an existing row - it does not create new accounts. The
table has other required columns (user_email_id, is_admin, audit
timestamps, ...) this script doesn't know how to fill in for a brand-new
user; create new accounts directly in the database instead.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Allow running this script directly (`python scripts/create_user.py`) by
# putting the backend/ directory on sys.path, the same root every other
# backend module already imports from (config., repositories., services...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.user_repository import user_repository  # noqa: E402


def reset_password(username: str, password: str) -> None:
    """Update the password for an existing user. Exits with an error if none exists."""

    updated = user_repository.set_password(username, password)

    if not updated:
        print(
            f"No user named '{username}' found in the users table. This script only "
            "resets passwords for existing accounts - create new rows directly in the database.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Updated password for user '{username}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Existing login username to reset the password for")
    args = parser.parse_args()

    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")

    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        sys.exit(1)

    reset_password(args.username, password)


if __name__ == "__main__":
    main()
