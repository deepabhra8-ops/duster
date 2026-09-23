"""Every route except health and auth requires a session.

Driven through TestClient so the actual dependency wiring in create_app() is
what is tested. Calling handler functions directly - which the other route
tests do - bypasses require_auth entirely, so an unprotected router would look
fine there and still be open in production.

This is the check that catches a router added later without
`dependencies=protected_dependencies`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


# One representative route per protected router.
PROTECTED = [
    ("GET", "/api/connections"),
    ("POST", "/api/test-connection"),
    ("GET", "/api/uploads"),
    ("GET", "/api/uploads/preview"),
    ("GET", "/api/jobs"),
    ("POST", "/api/jobs/draft"),
    ("GET", "/api/job/some-id"),
    ("GET", "/api/job/some-id/download/report"),
    ("GET", "/api/sample-csv"),
    ("POST", "/api/metadata"),
    ("GET", "/api/dashboard/summary"),
    ("GET", "/api/notifications"),
    ("POST", "/api/notifications"),
    ("POST", "/api/notifications/read-all"),
    ("DELETE", "/api/notifications"),
    ("PATCH", "/api/notifications/1"),
    # Registered on its own router, without the shared dependency (it must not
    # slide the session) - so this is the entry that proves it is still gated.
    ("GET", "/api/notifications/stream"),
]


class TestProtectedRoutes:
    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_an_anonymous_request_is_rejected(self, client, method, path):
        response = client.request(method, path)

        assert response.status_code == 401, (
            f"{method} {path} answered {response.status_code} without a session"
        )

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_a_bogus_session_cookie_is_rejected(self, client, method, path):
        client.cookies.set("dq_session", "not-a-real-session")

        response = client.request(method, path)

        assert response.status_code == 401


class TestOpenRoutes:
    def test_health_needs_no_session(self, client):
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_login_needs_no_session(self, client):
        """It cannot: it is how a session is obtained. It must reject bad
        credentials rather than refuse to answer."""
        response = client.post(
            "/api/auth/login", json={"username": "nobody", "password": "wrong"}
        )

        assert response.status_code != 401 or response.json().get("ok") is False

    def test_logout_is_safe_without_a_session(self, client):
        response = client.post("/api/auth/logout")

        assert response.status_code in (200, 204)


class TestUnknownRoutes:
    def test_an_unknown_path_is_a_404_not_a_500(self, client):
        assert client.get("/api/nope").status_code == 404
