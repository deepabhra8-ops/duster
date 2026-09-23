import inspect
import logging
import sys
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] %(message)s"

F = TypeVar("F", bound=Callable[..., Any])

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def get_request_id() -> str:
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
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
    return logging.getLogger(name)


def log_and_reraise(
    logger: logging.Logger,
    message: "str | Callable[..., tuple[Any, ...]] | None" = None,
) -> Callable[[F], F]:
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

        return wrapper

    return decorator
