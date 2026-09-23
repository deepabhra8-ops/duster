"""Configuration: env var loading plus every settings constant, re-exported here
so callers do `from core.config import X` without needing to know which
concern-specific submodule X actually lives in.

Split by concern (paths_config, pipeline_config, server_config, auth_config,
notifications_config, connections_config, metadata_scan_config,
rule_catalog_config, profile_map_config) - see each submodule for its own
constants and the reasoning behind them.
"""

from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Loads backend/.env if present (local dev). In a real deployment these same
# variable names are set by the environment / secrets manager instead, so
# nothing here changes when a key vault is introduced later (.env won't exist
# there, and load_dotenv() is a no-op when the file is missing regardless of
# override).
#
# override=True: a project-local .env should win over whatever the ambient
# shell/system environment happens to already have set for these same names -
# e.g. a stale system-wide JAVA_HOME shadowing the correct one a developer set
# in .env, silently, since load_dotenv()'s default is to never overwrite a
# variable that's already present.
load_dotenv(BASE_DIR / ".env", override=True)

from core.config.paths_config import (  # noqa: E402
    ACCEL_PATH,
    ACCEL_SRC_PATH,
    RULES_MASTER_PATH,
    RUNTIME_DIR,
    JOBS_DIR,
    UPLOADS_DIR,
    DATA_UPLOADS_DIR,
    LOV_UPLOADS_DIR,
    PROFILE_MAP_UPLOADS_DIR,
)
from core.config.pipeline_config import (  # noqa: E402
    MAX_UPLOAD_SIZE_BYTES,
    UPLOAD_KINDS,
    UPLOAD_KIND_LABELS,
    UPLOAD_ALLOWED_EXTENSIONS,
    PROFILE_MAP_EXTENSIONS,
    LOV_FILE_EXTENSION,
    STAGING_FILE_EXTENSION,
    JOB_ARCHIVE_THRESHOLD,
    DEFAULT_PROJECT_NAME,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_RUN_MODE,
    DEFAULT_CHUNK_SIZE,
    PROFILE_MAPPER_STEP,
    VALIDATOR_STEP,
    DEFAULT_DATABASE_CONNECT_TIMEOUT,
)
from core.config.server_config import (  # noqa: E402
    API_PREFIX,
    HOST,
    PORT,
    DEBUG,
    THREADED,
    ALLOWED_ORIGINS,
)
from core.config.auth_config import (  # noqa: E402
    DATABASE_URL,
    USERS_TABLE_SCHEMA,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    SESSION_COOKIE_SECURE,
    AUTH_ALLOW_LEGACY_PLAINTEXT,
)
from core.config.notifications_config import (  # noqa: E402
    NOTIFICATION_STREAM_POLL_SECONDS,
    NOTIFICATION_RETENTION_DAYS,
    RUN_NOTIFICATION_PURGE,
)
from core.config.connections_config import CONNECTION_ENCRYPTION_KEY  # noqa: E402
from core.config.metadata_scan_config import (  # noqa: E402
    METADATA_SCAN_MAX_SCHEMAS,
    METADATA_SCAN_MAX_TABLES_PER_SCHEMA,
)
from core.config.rule_catalog_config import VALID_RULE_IDS  # noqa: E402
from core.config.profile_map_config import (  # noqa: E402
    PROFILE_MAP_EDITABLE_FIELDS,
    PROFILE_MAP_TEXT_FIELD_MAX_LEN,
    PROFILE_MAP_NOTES_MAX_LEN,
)

__all__ = [
    "BASE_DIR",
    "ACCEL_PATH", "ACCEL_SRC_PATH", "RULES_MASTER_PATH", "RUNTIME_DIR",
    "JOBS_DIR", "UPLOADS_DIR", "DATA_UPLOADS_DIR", "LOV_UPLOADS_DIR",
    "PROFILE_MAP_UPLOADS_DIR",
    "MAX_UPLOAD_SIZE_BYTES", "UPLOAD_KINDS", "UPLOAD_KIND_LABELS",
    "UPLOAD_ALLOWED_EXTENSIONS", "PROFILE_MAP_EXTENSIONS", "LOV_FILE_EXTENSION",
    "STAGING_FILE_EXTENSION", "JOB_ARCHIVE_THRESHOLD", "DEFAULT_PROJECT_NAME",
    "DEFAULT_SOURCE_TYPE", "DEFAULT_RUN_MODE", "DEFAULT_CHUNK_SIZE",
    "PROFILE_MAPPER_STEP", "VALIDATOR_STEP", "DEFAULT_DATABASE_CONNECT_TIMEOUT",
    "API_PREFIX", "HOST", "PORT", "DEBUG", "THREADED", "ALLOWED_ORIGINS",
    "DATABASE_URL", "USERS_TABLE_SCHEMA", "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS", "SESSION_COOKIE_SECURE", "AUTH_ALLOW_LEGACY_PLAINTEXT",
    "NOTIFICATION_STREAM_POLL_SECONDS", "NOTIFICATION_RETENTION_DAYS",
    "RUN_NOTIFICATION_PURGE",
    "CONNECTION_ENCRYPTION_KEY",
    "METADATA_SCAN_MAX_SCHEMAS", "METADATA_SCAN_MAX_TABLES_PER_SCHEMA",
    "VALID_RULE_IDS",
    "PROFILE_MAP_EDITABLE_FIELDS", "PROFILE_MAP_TEXT_FIELD_MAX_LEN",
    "PROFILE_MAP_NOTES_MAX_LEN",
]
