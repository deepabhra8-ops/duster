"""HTTP server and CORS settings."""

import os


API_PREFIX = "/api"

HOST = "127.0.0.1"
PORT = 5050
DEBUG = False
THREADED = True


_DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = (
    [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
    if _cors_env
    else list(_DEFAULT_ALLOWED_ORIGINS)
)
