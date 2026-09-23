"""Auth / session settings."""

import os


# DATABASE_URL is the app's user-account store (a SQLAlchemy URL, e.g.
# mssql+pyodbc://user:password@host:1433/dbname?driver=ODBC+Driver+18+for+SQL+Server).
# Set it in backend/.env (gitignored, never committed) - see backend/.env.example.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Schema holding the `users` table (see repositories/user_repository.py).
# Defaults to "dbo"; override in backend/.env if that table lives elsewhere.
USERS_TABLE_SCHEMA = os.getenv("USERS_TABLE_SCHEMA", "dbo")

SESSION_COOKIE_NAME = "dq_session"

# Sliding/rolling expiry: every authenticated request extends the session by
# this many seconds, so an active user is never logged out mid-work - only
# real inactivity past this window (or an explicit sign-out) ends it.
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(8 * 60 * 60)))

# Set SESSION_COOKIE_SECURE=true once the app is served over HTTPS. False by
# default so the cookie still works for local http://localhost dev.
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"

# Whether a login may verify against a stored password that is still plaintext
# (common/security/password_hash.verify_password). On by default because the
# `users` table is externally managed: another system can insert a plaintext row
# at any time, and rejecting those locks real people out rather than fixing
# anything. Each such login is logged as a warning and the row is rewritten as a
# hash immediately, so the population self-heals. Set false to fail closed once
# nothing but this app writes to that table.
AUTH_ALLOW_LEGACY_PLAINTEXT = (
    os.getenv("AUTH_ALLOW_LEGACY_PLAINTEXT", "true").strip().lower() == "true"
)
