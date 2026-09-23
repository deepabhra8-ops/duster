"""Caches SQLAlchemy engines used for metadata discovery, keyed by connection string.

metadata_routes.py fields one request per schema/table/column lookup - and the
Configure page fires one of these per configured table row, per debounced
keystroke. Without caching, each of those calls built a brand-new engine and
opened (then immediately closed) a fresh authenticated connection, so a page
with a few table rows could issue several real login attempts to the same
database within the same second. Against a database that locks the account
after N failed logins (e.g. Redshift), that amplification turns one bad
password into an account lockout almost immediately. Reusing a pooled engine
per connection string means only the first lookup for a given connection
authenticates fresh; subsequent lookups reuse a pooled connection instead of
opening a new one.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from utils.logger import get_logger


logger = get_logger(__name__)

# How long an idle cached engine is kept before being disposed and rebuilt.
# Keeps credentials from going stale forever in memory while still avoiding
# a fresh login per request for the common case (a user actively configuring
# a job over a few minutes).
_ENGINE_TTL_SECONDS = 15 * 60

_engines: dict[str, tuple[Engine, float]] = {}
_lock = Lock()


def get_cached_engine(connection_string: str) -> Engine:
    """Return a pooled engine for this connection string, creating (or refreshing) it as needed."""
    now = time.monotonic()

    with _lock:
        cached = _engines.get(connection_string)

        if cached is not None:
            engine, created_at = cached

            if now - created_at < _ENGINE_TTL_SECONDS:
                return engine

            _dispose_quietly(engine)

        engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            pool_recycle=280,
            pool_size=5,
            max_overflow=5,
        )

        _engines[connection_string] = (engine, now)
        logger.debug("Created and cached metadata engine")
        return engine


def _dispose_quietly(engine: Engine) -> None:
    try:
        engine.dispose()
    except Exception:
        logger.exception("Failed to dispose expired metadata engine")
