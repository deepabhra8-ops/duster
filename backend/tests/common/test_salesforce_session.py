"""Tests for the shared Salesforce HTTP session: timeouts, retries, error wording."""
from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
from urllib3.util.retry import Retry

from common import salesforce_session

from common.salesforce_session import (
    CONNECT_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    build_salesforce_session,
    describe_salesforce_error,
)


class TestTimeouts:
    """The override delegates to requests.Session.request, so that is what is
    patched - via mock.patch, which restores it afterwards. Assigning to
    requests.Session.request directly would leak the stub into every other test
    in the process."""

    def test_every_request_gets_a_default_timeout(self):
        """The regression this prevents: simple_salesforce builds a bare Session
        with no timeout, so a hung endpoint blocks the caller forever."""
        session = build_salesforce_session()

        with patch.object(requests.Session, "request", return_value="sent") as parent:
            session.request("GET", "https://example.invalid")

        assert parent.call_args.kwargs["timeout"] == (
            CONNECT_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
        )

    def test_an_explicit_timeout_is_not_overridden(self):
        session = build_salesforce_session()

        with patch.object(requests.Session, "request", return_value="sent") as parent:
            session.request("GET", "https://example.invalid", timeout=(1, 2))

        assert parent.call_args.kwargs["timeout"] == (1, 2)


class TestRetries:
    @pytest.mark.parametrize("scheme", ["https://", "http://"])
    def test_adapters_carry_bounded_retries(self, scheme):
        retries = build_salesforce_session().get_adapter(f"{scheme}x").max_retries

        assert retries.total == 3
        assert retries.backoff_factor > 0

    def test_rate_limit_and_server_errors_are_retried(self):
        forcelist = build_salesforce_session().get_adapter("https://x").max_retries.status_forcelist

        # 429 is Salesforce's rate-limit response; 5xx are transient.
        assert 429 in forcelist
        assert 503 in forcelist

    def test_retry_after_is_respected(self):
        """Salesforce tells us how long to wait on a 429 - honouring it is the
        difference between backing off and hammering an already-throttled org."""
        assert build_salesforce_session().get_adapter("https://x").max_retries.respect_retry_after_header


class TestOlderUrllib3:
    """AWS Glue ships a urllib3 older than 1.26, where the kwarg naming the
    retriable methods is `method_whitelist` rather than `allowed_methods`.

    This is not a theoretical compatibility note. Passing the newer name there
    raised TypeError while this module was being imported, and because the
    engine imports it transitively from data_sources/__init__, that single
    keyword failed *every* Glue run - profiling and validation, Salesforce
    source or not - before a row was read.
    """

    @staticmethod
    def _old_retry_class():
        class OldRetry(Retry):
            def __init__(self, *args, allowed_methods=None, **kwargs):
                if allowed_methods is not None:
                    raise TypeError(
                        "Retry.__init__() got an unexpected keyword argument "
                        "'allowed_methods'"
                    )
                kwargs.pop("method_whitelist", None)
                super().__init__(*args, **kwargs)

        return OldRetry

    def test_a_session_is_still_built(self, monkeypatch):
        monkeypatch.setattr(salesforce_session, "Retry", self._old_retry_class())

        session = build_salesforce_session()

        assert session is not None
        assert session.get_adapter("https://x").max_retries.total == 3

    def test_timeouts_survive_the_fallback(self, monkeypatch):
        monkeypatch.setattr(salesforce_session, "Retry", self._old_retry_class())

        session = build_salesforce_session()

        assert session._timeout == (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)

    def test_a_session_is_built_even_with_no_usable_retry_api(self, monkeypatch):
        """Last resort: a Salesforce connection without retries is still a
        working connection. Nothing about retry configuration justifies taking
        the engine down."""
        def unusable(*args, **kwargs):
            raise TypeError("nothing here is supported")

        monkeypatch.setattr(salesforce_session, "Retry", unusable)

        assert build_salesforce_session() is not None


class TestErrorMessages:
    def test_api_limit_is_explained_in_plain_language(self):
        message = describe_salesforce_error(Exception("REQUEST_LIMIT_EXCEEDED: TotalRequests"))

        assert message is not None
        assert "request limit" in message.lower()

    def test_expired_session_is_explained(self):
        message = describe_salesforce_error(Exception("INVALID_SESSION_ID: Session expired"))

        assert message is not None
        assert "expired" in message.lower()

    def test_an_ordinary_error_is_left_alone(self):
        """Only conditions an operator can act on get reworded; everything else
        keeps its original traceback rather than being flattened into prose."""
        assert describe_salesforce_error(ValueError("something else broke")) is None
