from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repositories.user_repository import user_repository


def reset_password(username: str, password: str) -> None:
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
    parser = argparse.ArgumentParser(description="Reset the password of an existing login account in the users table.")
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
