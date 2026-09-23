"""Upload handling and DQ pipeline defaults."""

MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024

UPLOAD_KINDS = (
    "data",
    "lov",
    "profile_map",
)

UPLOAD_KIND_LABELS = {
    "data": "Flat File Source",
    "lov": "LOV",
    "profile_map": "Profile Map",
}

# Server-side mirror of frontend/src/constants/appConfig.js's UPLOAD_ALLOWED_EXT.
# The frontend check is UX only (a curl/Postman request skips it entirely), so
# this is the actual enforcement point - see UploadFileSaver._validate_extension.
UPLOAD_ALLOWED_EXTENSIONS = {
    "data": (".csv", ".xlsx"),
    "lov": (".csv",),
    "profile_map": (".xlsx",),
}

PROFILE_MAP_EXTENSIONS = (
    ".xlsx",
    ".xls",
)

LOV_FILE_EXTENSION = ".csv"
STAGING_FILE_EXTENSION = ".csv"

JOB_ARCHIVE_THRESHOLD = 100


DEFAULT_PROJECT_NAME = "SMART_DataHub"
DEFAULT_SOURCE_TYPE = "csv"
DEFAULT_RUN_MODE = 1
DEFAULT_CHUNK_SIZE = 50000

PROFILE_MAPPER_STEP = "1"
VALIDATOR_STEP = "3"


DEFAULT_DATABASE_CONNECT_TIMEOUT = 8
