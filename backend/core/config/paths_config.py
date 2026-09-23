"""Filesystem layout constants: where the app's source, rules, and runtime data live."""

from core.config import BASE_DIR


ACCEL_PATH = BASE_DIR
ACCEL_SRC_PATH = BASE_DIR / "src"
RULES_MASTER_PATH = BASE_DIR / "rules" / "DQ_Rules_Master.xlsx"


RUNTIME_DIR = BASE_DIR.parent / "runtime"

JOBS_DIR = RUNTIME_DIR / "jobs"
UPLOADS_DIR = RUNTIME_DIR / "uploads"

DATA_UPLOADS_DIR = UPLOADS_DIR / "data"
LOV_UPLOADS_DIR = UPLOADS_DIR / "lov"
PROFILE_MAP_UPLOADS_DIR = UPLOADS_DIR / "profile_map"
