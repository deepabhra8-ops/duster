"""Shared application logging utilities: console log setup, request correlation, and an exception-logging decorator used across the backend.

Every log line carries the id of the request that produced it. Without that,
four Uvicorn workers interleave their output into one stream and there is no way
to tell which lines belong together - so diagnosing a single failed request
means guessing from timestamps. The id is also returned to the caller as the
X-Request-ID response header, which is what lets a user's bug report be tied to
the exact lines in the log.

The id lives in a ContextVar rather than being threaded through call arguments:
it has to reach logging call sites several layers deep (repositories, connectors)
that have no business knowing about HTTP, and a ContextVar follows both async
tasks and threads without touching any of those signatures.
"""

import inspect
import logging
import sys
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"

F = TypeVar("F", bound=Callable[..., Any])

# "-" for anything outside a request: startup, the migration runner, CLI scripts.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Return a short, unique id for one request."""
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    """Bind a request id to the current context, for the logging filter to pick up."""
    _request_id.set(request_id)


def get_request_id() -> str:
    """Return the current context's request id, or '-' outside a request."""
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    """Adds request_id to every record so LOG_FORMAT can render it.

    A filter rather than a custom Formatter: records emitted by third-party
    libraries (uvicorn, sqlalchemy, botocore) never set the attribute
    themselves, and a format string referencing a missing attribute raises.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
    """Configure application logs to be written to the console in UTF-8."""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[handler],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for use by application modules."""

    return logging.getLogger(name)


def log_and_reraise(
    logger: logging.Logger,
    message: "str | Callable[..., tuple[Any, ...]] | None" = None,
) -> Callable[[F], F]:
    """Decorator that logs an unhandled exception via logger.exception(), then re-raises it unchanged."""

    def decorator(func: F) -> F:
        signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception:
                if callable(message):
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                    logger.exception(*message(**bound.arguments))
                elif message:
                    logger.exception(message)
                else:
                    logger.exception("%s failed", func.__qualname__)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
