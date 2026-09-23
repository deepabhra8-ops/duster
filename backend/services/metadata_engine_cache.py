from __future__ import annotations

import time
from threading import Lock
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from utils.logger import get_logger


logger = get_logger(__name__)

_ENGINE_TTL_SECONDS = 15 * 60

_engines: dict[str, tuple[Engine, float]] = {}
_lock = Lock()


def get_cached_engine(connection_string: str) -> Engine:
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
