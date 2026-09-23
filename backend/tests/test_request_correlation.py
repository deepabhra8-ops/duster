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
        response = client.get("/api/health", headers={"X-Request-ID": "upstream-123"})

        assert response.headers["x-request-id"] == "upstream-123"


class TestLogCorrelation:
    def test_log_lines_carry_the_request_id(self, client, caplog):
        with caplog.at_level(logging.INFO):
            request_id = client.get("/api/health").headers["x-request-id"]

        ids = {getattr(record, "request_id", None) for record in caplog.records}

        assert request_id in ids

    def test_outside_a_request_the_id_is_a_placeholder(self):
        seen = []

        thread = threading.Thread(target=lambda: seen.append(get_request_id()))
        thread.start()
        thread.join()

        assert seen == ["-"]


class TestErrorPath:
    def test_a_failing_request_still_returns_its_id(self, client, monkeypatch):
        import routes.health_routes as health_routes

        def explode():
            raise RuntimeError("boom")

        monkeypatch.setattr(health_routes, "health", explode, raising=False)

        response = client.get("/api/does-not-exist")

        assert response.headers.get("x-request-id")
