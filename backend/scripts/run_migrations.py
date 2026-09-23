from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from core.db import get_engine
from core.config import BASE_DIR


MIGRATIONS_DIR = BASE_DIR / "migrations"

_TRACKING_TABLE_DDL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schema_migrations')
BEGIN
    CREATE TABLE schema_migrations (
        filename    VARCHAR(255) PRIMARY KEY,
        applied_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    )
END
"""

_BATCH_SEPARATOR = re.compile(r"(?m)^\s*GO\s*$", re.IGNORECASE)


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []

    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def applied_filenames(engine) -> set[str]:
    with engine.begin() as conn:
        conn.execute(text(_TRACKING_TABLE_DDL))

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT filename FROM schema_migrations"))
        return {row[0] for row in rows}


def apply_migration(engine, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")

    with engine.begin() as conn:
        for batch in _BATCH_SEPARATOR.split(sql):
            statement = batch.strip()
            if statement:
                conn.execute(text(statement))

        conn.execute(
            text(
                "IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE filename = :filename) "
                "INSERT INTO schema_migrations (filename) VALUES (:filename)"
            ),
            {"filename": path.name},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations to the configured database.")
    parser.add_argument("--status", action="store_true", help="show state, change nothing")
    parser.add_argument("--dry-run", action="store_true", help="list pending, change nothing")
    args = parser.parse_args()

    files = migration_files()

    if not files:
        print(f"No migration files found in {MIGRATIONS_DIR}")
        return 0

    try:
        engine = get_engine()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Set DATABASE_URL in backend/.env (see backend/.env.example).", file=sys.stderr)
        return 1

    applied = applied_filenames(engine)
    pending = [path for path in files if path.name not in applied]

    if args.status or args.dry_run:
        for path in files:
            marker = "applied" if path.name in applied else "PENDING"
            print(f"  [{marker:>7}] {path.name}")
        print()
        print(f"{len(pending)} pending, {len(applied)} applied.")
        return 0

    if not pending:
        print(f"Database is up to date ({len(applied)} migration(s) applied).")
        return 0

    print(f"Applying {len(pending)} migration(s)...")

    for path in pending:
        print(f"  {path.name} ... ", end="", flush=True)
        try:
            apply_migration(engine, path)
        except Exception as exc:
            print("FAILED")
            print(f"\nERROR applying {path.name}: {exc}", file=sys.stderr)
            print("No changes from this file were kept.", file=sys.stderr)
            return 1
        print("ok")

    print(f"\nDone. {len(pending)} migration(s) applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
