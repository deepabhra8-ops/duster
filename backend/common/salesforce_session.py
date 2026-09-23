"""A requests Session for Salesforce with timeouts and bounded retries.

simple_salesforce builds its own bare requests.Session when none is supplied,
which means no connect or read timeout at all: a hung Salesforce endpoint parks
the calling thread indefinitely - a Uvicorn worker (or the background thread
running the DQ engine) taken out of service, with nothing to reconcile it.

Shared by the API layer and the engine on purpose. The engine package is
deliberately kept importable without the rest of the backend (some deployment
modes ship the web tier without engine/ at all - see job_runner.py/
pipeline_service.py's deferred engine imports), so this module lives in
common/, not services/, as the one place both sides can agree on connection
behaviour.

Retries are deliberately narrow. 429 and 5xx are transient and worth retrying
with backoff - urllib3 honours Salesforce's Retry-After header on a 429. A
daily API-limit breach (REQUEST_LIMIT_EXCEEDED) is not transient and is not
retried here: hammering an exhausted org only burns the next day's quota too,
so it surfaces as an error for a human to act on.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.logger import get_logger


logger = get_logger(__name__)


# Connect fast-fail; read allows for Salesforce's slower query responses.
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 120

_RETRY_STATUSES = (429, 500, 502, 503, 504)
_RETRY_METHODS = frozenset({"GET", "POST"})


def _build_retry() -> Retry | None:
    """Build the retry policy, tolerating urllib3's rename of one argument.

    The argument naming the retriable HTTP methods was `method_whitelist` until
    urllib3 1.26, which added `allowed_methods` and later removed the old name.
    AWS Glue's runtime ships a urllib3 older than that, so passing
    `allowed_methods` there raises TypeError.

    That mattered far more than it sounds: this module is imported (via
    data_sources/__init__) by every engine entry point, so building the policy
    at module scope turned one incompatible keyword into an ImportError that
    failed *every* Glue run - profiling and validation alike, Salesforce or not.
    Hence both the fallbacks and the None return: no configuration problem here
    is worth taking the engine down for, and a session without retries still
    works.
    """
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
        # Neither name is accepted - take the defaults rather than give up.
        return Retry(total=3, backoff_factor=1.5, status_forcelist=_RETRY_STATUSES)
    except Exception:
        logger.warning(
            "Could not configure HTTP retries for Salesforce; continuing without them",
            exc_info=True,
        )
        return None


class _TimeoutSession(requests.Session):
    """A Session that applies a default timeout to every request.

    requests has no session-level timeout setting - it is a per-call argument,
    and simple_salesforce does not pass one. Overriding request() is the only
    way to make every call it makes bounded without forking the library.
    """

    def __init__(self, timeout: tuple[int, int]) -> None:
        super().__init__()
        self._timeout = timeout

    def request(self, method, url, **kwargs):  # type: ignore[override]
        kwargs.setdefault("timeout", self._timeout)
        return super().request(method, url, **kwargs)


def build_salesforce_session() -> requests.Session:
    """Return a Session with default timeouts and retry/backoff configured.

    Built per call rather than from module-level state so that nothing here can
    fail at import time - see _build_retry for why that distinction cost every
    Glue run once already.
    """
    session = _TimeoutSession((CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS))

    retry = _build_retry()
    adapter = HTTPAdapter(max_retries=retry) if retry is not None else HTTPAdapter()

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def describe_salesforce_error(exc: BaseException) -> str | None:
    """Return a plain-language message for a Salesforce API-limit failure, else None.

    Salesforce reports an exhausted request allocation as REQUEST_LIMIT_EXCEEDED,
    which otherwise reaches the user as an opaque library exception that reads
    like a bug rather than a quota.
    """
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
