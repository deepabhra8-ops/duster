import os


DATABASE_URL = os.getenv("DATABASE_URL", "")

USERS_TABLE_SCHEMA = os.getenv("USERS_TABLE_SCHEMA", "dbo")

SESSION_COOKIE_NAME = "dq_session"

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(8 * 60 * 60)))

SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() == "true"

AUTH_ALLOW_LEGACY_PLAINTEXT = (
    os.getenv("AUTH_ALLOW_LEGACY_PLAINTEXT", "true").strip().lower() == "true"
)
