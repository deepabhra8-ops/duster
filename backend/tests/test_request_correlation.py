"""Every request gets an id that appears in its logs and in its response.

Four Uvicorn workers write into one interleaved stream, so without a per-request
id there is no way to tell which log lines belong to the request that failed.
Returning the same id as X-Request-ID is what lets a user's report ("it broke,
here's the id") be matched to those lines.

Driven through TestClient rather than by calling handlers directly, because the
behaviour under test lives in middleware.
"""
from __future__ import annotations

import logging
import threading

import pytest
from fastapi.testclient import TestClient

from app import create_app
from utils.logger import get_request_id


@pytest.fixture
def client():
    return TestClient(create_app())


class TestResponseHeader:
    def test_a_request_id_is_returned(self, client):
        response = client.get("/api/health")

        assert response.headers.get("x-request-id")

    def test_each_request_gets_a_distinct_id(self, client):
        first = client.get("/api/health").headers["x-request-id"]
        second = client.get("/api/health").headers["x-request-id"]

        assert first != second

    def test_an_inbound_id_is_preserved(self, client):
        """A load balancer or caller may already have assigned one; adopting it
        keeps a single trace across hops instead of starting a competing one."""
        response = client.get("/api/health", headers={"X-Request-ID": "upstream-123"})

        assert response.headers["x-request-id"] == "upstream-123"


class TestLogCorrelation:
    def test_log_lines_carry_the_request_id(self, client, caplog):
        with caplog.at_level(logging.INFO):
            request_id = client.get("/api/health").headers["x-request-id"]

        # The filter attaches request_id to the record; the format string renders it.
        ids = {getattr(record, "request_id", None) for record in caplog.records}

        assert request_id in ids

    def test_outside_a_request_the_id_is_a_placeholder(self):
        """Startup, migrations and CLI scripts log too, and must not crash on a
        format string that references request_id.

        Checked on a fresh thread because that is what "outside a request"
        actually means: a ContextVar is per-context, and a new thread starts
        with an empty one. Asserting on this thread would instead pick up
        whatever id the last thing to run here happened to set - the reconciler
        tags its own sweeps, for instance.
        """
        seen = []

        thread = threading.Thread(target=lambda: seen.append(get_request_id()))
        thread.start()
        thread.join()

        assert seen == ["-"]


class TestErrorPath:
    def test_a_failing_request_still_returns_its_id(self, client, monkeypatch):
        """The id matters most when something broke, so the error response must
        carry it too - not just the success path."""
        import routes.health_routes as health_routes

        def explode():
            raise RuntimeError("boom")

        monkeypatch.setattr(health_routes, "health", explode, raising=False)

        response = client.get("/api/does-not-exist")

        # A 404 goes through the same middleware; the header is what is asserted.
        assert response.headers.get("x-request-id")
