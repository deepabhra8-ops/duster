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
    def test_every_request_gets_a_default_timeout(self):
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

        assert 429 in forcelist
        assert 503 in forcelist

    def test_retry_after_is_respected(self):
        assert build_salesforce_session().get_adapter("https://x").max_retries.respect_retry_after_header


class TestOlderUrllib3:
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
        assert describe_salesforce_error(ValueError("something else broke")) is None
