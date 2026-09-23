from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger


logger = get_logger(__name__)


CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 120

_RETRY_STATUSES = (429, 500, 502, 503, 504)
_RETRY_METHODS = frozenset({"GET", "POST"})


def _build_retry() -> Retry | None:
    common = {
        "total": 3,
        "backoff_factor": 1.5,
        "status_forcelist": _RETRY_STATUSES,
        "respect_retry_after_header": True,
        "raise_on_status": False,
    }

    for methods_kwarg in ("allowed_methods", "method_whitelist"):
        try:
            return Retry(**common, **{methods_kwarg: _RETRY_METHODS})
        except TypeError:
            continue

    try:
        return Retry(total=3, backoff_factor=1.5, status_forcelist=_RETRY_STATUSES)
    except Exception:
        logger.warning(
            "Could not configure HTTP retries for Salesforce; continuing without them",
            exc_info=True,
        )
        return None


class _TimeoutSession(requests.Session):
    def __init__(self, timeout: tuple[int, int]) -> None:
        super().__init__()
        self._timeout = timeout

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().request(method, url, **kwargs)


def build_salesforce_session() -> requests.Session:
    session = _TimeoutSession((CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS))

    retry = _build_retry()
    adapter = HTTPAdapter(max_retries=retry) if retry is not None else HTTPAdapter()

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def describe_salesforce_error(exc: BaseException) -> str | None:
    text = str(exc)

    if "REQUEST_LIMIT_EXCEEDED" in text:
        return (
            "Salesforce API request limit exceeded for this org. The limit resets "
            "on a rolling 24-hour window - retry later, or reduce how much data "
            "this job reads."
        )

    if "INVALID_SESSION_ID" in text:
        return "The Salesforce session expired or was revoked. Re-test the connection."

    return None
