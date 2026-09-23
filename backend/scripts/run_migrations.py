"""Apply pending SQL migrations to the configured database.

Until now migrations were applied by hand, with nothing recording which had run.
That is how the schema silently fell behind the code: the app queried columns that
migration 002 adds, got `UndefinedColumn`, and surfaced raw 500s with no hint that
a migration was outstanding.

Usage, from the backend/ directory:

    python scripts/run_migrations.py            # apply anything pending
    python scripts/run_migrations.py --status   # show applied vs pending, change nothing
    python scripts/run_migrations.py --dry-run  # list what would be applied

Applied filenames are recorded in `schema_migrations`, so re-running is a no-op.
Each file is executed in its own transaction and rolled back as a unit on failure.
The migrations themselves are also written to be individually idempotent, so a
database already migrated by hand can be adopted without being re-applied.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow running this file directly from backend/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from core.db import get_engine  # noqa: E402
from core.config import BASE_DIR  # noqa: E402


MIGRATIONS_DIR = BASE_DIR / "migrations"

# T-SQL's `TIMESTAMP` is a legacy rowversion type, not a datetime type - using
# it here would silently give this column the wrong meaning entirely.
_TRACKING_TABLE_DDL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'schema_migrations')
BEGIN
    CREATE TABLE schema_migrations (
        filename    VARCHAR(255) PRIMARY KEY,
        applied_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    )
END
"""

# The standard T-SQL batch separator. A migration file that needs one (e.g.
# because it contains a CREATE TRIGGER, which SQL Server requires to be the
# only statement in its batch) puts `GO` alone on a line; a file with no `GO`
# at all is just one batch, same as before.
_BATCH_SEPARATOR = re.compile(r"(?m)^\s*GO\s*$", re.IGNORECASE)


def migration_files() -> list[Path]:
    """Return every migration file, in filename order (001_, 002_, ...)."""
    if not MIGRATIONS_DIR.is_dir():
        return []

    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def applied_filenames(engine) -> set[str]:
    """Return the set of migrations already recorded as applied."""
    with engine.begin() as conn:
        conn.execute(text(_TRACKING_TABLE_DDL))

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT filename FROM schema_migrations"))
        return {row[0] for row in rows}


def apply_migration(engine, path: Path) -> None:
    """Run one migration file and record it, as a single transaction.

    Split into batches on `GO` (SQL Server requires some statements, like
    CREATE TRIGGER, to be alone in their batch) and executed in order on one
    connection, so the file stays atomic even though it's multiple statements.
    """
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
    parser = argparse.ArgumentParser(description=__doc__)
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
