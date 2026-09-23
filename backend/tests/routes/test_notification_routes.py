"""Notification endpoints, driven through TestClient so the real routing is what runs.

Auth is overridden to a fixed user: the gate itself is covered by test_auth_gate.py.
Services are patched, so no database is touched. The stream is the exception to
"driven through TestClient" - see the note on that class.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import create_app
from routes import notification_routes
from routes.auth_routes import require_auth
from services import auth_service as auth_service_module
from services.notification_service import (
    NotificationPermissionError,
    NotificationValidationError,
)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[require_auth] = lambda: "alice"
    return TestClient(app)


PAGE = {"items": [{"id": 3, "status": "unread"}], "unread_count": 1, "next_cursor": None}


class TestList:
    def test_returns_the_page_in_the_standard_envelope(self, client):
        with patch.object(notification_routes.notification_service, "list_for", return_value=PAGE) as list_for:
            response = client.get("/api/notifications")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "data": PAGE}
        list_for.assert_called_once_with("alice", 20, None, False)

    def test_passes_limit_cursor_and_unread_filter_through(self, client):
        with patch.object(notification_routes.notification_service, "list_for", return_value=PAGE) as list_for:
            client.get("/api/notifications?limit=5&before=42&unread=true")

        list_for.assert_called_once_with("alice", 5, 42, True)

    @pytest.mark.parametrize("query", ["limit=abc", "before=x", "limit=0", "limit=-1", "before=0", "before=-3"])
    def test_rejects_bad_paging_parameters(self, client, query):
        with patch.object(notification_routes.notification_service, "list_for") as list_for:
            response = client.get(f"/api/notifications?{query}")

        assert response.status_code == 400
        assert response.json()["ok"] is False
        list_for.assert_not_called()

    def test_a_failure_is_a_500_that_does_not_leak_the_cause(self, client):
        with patch.object(
            notification_routes.notification_service, "list_for", side_effect=RuntimeError("password=hunter2")
        ):
            response = client.get("/api/notifications")

        assert response.status_code == 500
        assert "hunter2" not in response.text


class TestCreate:
    BODY = {"type": "info", "title": "Hello", "content": "World", "link": "/home"}

    def test_creates_and_returns_201(self, client):
        created = {"id": 9, **self.BODY, "status": "unread"}

        with patch.object(notification_routes.notification_service, "create", return_value=created) as create:
            response = client.post("/api/notifications", json=self.BODY)

        assert response.status_code == 201
        assert response.json() == {"ok": True, "data": created}
        create.assert_called_once_with(
            "alice", type="info", title="Hello", content="World", link="/home", username=None
        )

    def test_the_requester_comes_from_the_session_never_the_body(self, client):
        """A body `username` is only a request to notify someone else, which the service
        then allows or refuses. It must never be able to stand in for who is asking."""
        with patch.object(notification_routes.notification_service, "create", return_value={}) as create:
            client.post("/api/notifications", json={**self.BODY, "username": "bob", "requester": "admin"})

        assert create.call_args.args == ("alice",)
        assert create.call_args.kwargs["username"] == "bob"

    def test_validation_errors_are_a_400_with_the_reason(self, client):
        with patch.object(
            notification_routes.notification_service,
            "create",
            side_effect=NotificationValidationError("title is required"),
        ):
            response = client.post("/api/notifications", json={"type": "info"})

        assert response.status_code == 400
        assert response.json() == {"ok": False, "error": "title is required"}

    def test_notifying_someone_else_without_rights_is_a_403(self, client):
        with patch.object(
            notification_routes.notification_service,
            "create",
            side_effect=NotificationPermissionError("Only an administrator can create notifications for other users"),
        ):
            response = client.post("/api/notifications", json={**self.BODY, "username": "bob"})

        assert response.status_code == 403
        assert response.json()["ok"] is False

    @pytest.mark.parametrize("body", [[1, 2], "text", 5, None])
    def test_a_body_that_is_not_a_json_object_is_a_400(self, client, body):
        response = client.post("/api/notifications", json=body)

        assert response.status_code == 400

    def test_malformed_json_is_a_400_not_a_500(self, client):
        response = client.post(
            "/api/notifications", content="{not json", headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

    def test_an_unexpected_failure_is_a_generic_500(self, client):
        with patch.object(
            notification_routes.notification_service, "create", side_effect=RuntimeError("internal detail")
        ):
            response = client.post("/api/notifications", json=self.BODY)

        assert response.status_code == 500
        assert "internal detail" not in response.text


class TestMarkRead:
    def test_marks_read_and_returns_the_new_count(self, client):
        result = {"notification": {"id": 3, "status": "read"}, "unread_count": 2}

        with patch.object(notification_routes.notification_service, "mark_read", return_value=result) as mark:
            response = client.patch("/api/notifications/3", json={"status": "read"})

        assert response.status_code == 200
        assert response.json() == {"ok": True, "data": result}
        mark.assert_called_once_with("alice", 3)

    def test_not_found_or_not_yours_is_a_404(self, client):
        with patch.object(notification_routes.notification_service, "mark_read", return_value=None):
            response = client.patch("/api/notifications/3", json={"status": "read"})

        assert response.status_code == 404

    @pytest.mark.parametrize("bad_id", ["abc", "0", "-4", "1.5"])
    def test_an_id_that_cannot_match_a_row_is_a_404_without_touching_the_service(self, client, bad_id):
        with patch.object(notification_routes.notification_service, "mark_read") as mark:
            response = client.patch(f"/api/notifications/{bad_id}", json={"status": "read"})

        assert response.status_code == 404
        mark.assert_not_called()

    @pytest.mark.parametrize("body", [{"status": "unread"}, {"status": ""}, {}, {"foo": 1}, [1]])
    def test_anything_but_status_read_is_refused_not_ignored(self, client, body):
        with patch.object(notification_routes.notification_service, "mark_read") as mark:
            response = client.patch("/api/notifications/3", json=body)

        assert response.status_code == 400
        mark.assert_not_called()


class TestMarkAllRead:
    def test_marks_everything_read(self, client):
        with patch.object(
            notification_routes.notification_service, "mark_all_read", return_value={"updated": 4, "unread_count": 0}
        ) as mark_all:
            response = client.post("/api/notifications/read-all")

        assert response.status_code == 200
        assert response.json()["data"] == {"updated": 4, "unread_count": 0}
        mark_all.assert_called_once_with("alice")

    def test_is_not_swallowed_by_the_id_route(self, client):
        """'read-all' shares a prefix with '/{id}'. It must be routed, not read as an id (which
        would 404) nor rejected as a wrong method (405)."""
        with patch.object(
            notification_routes.notification_service, "mark_all_read", return_value={"updated": 0, "unread_count": 0}
        ):
            assert client.post("/api/notifications/read-all").status_code == 200


class TestClearAll:
    def test_clears_the_callers_notifications(self, client):
        result = {"deleted": 12, "unread_count": 0}

        with patch.object(notification_routes.notification_service, "clear_all", return_value=result) as clear:
            response = client.delete("/api/notifications")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "data": result}
        clear.assert_called_once_with("alice")

    def test_the_user_comes_from_the_session_never_the_request(self, client):
        """There is nothing in the request that could name another user - but prove a hostile
        query string or body cannot smuggle one in."""
        with patch.object(
            notification_routes.notification_service, "clear_all", return_value={"deleted": 0, "unread_count": 0}
        ) as clear:
            client.request("DELETE", "/api/notifications?username=bob", json={"username": "bob"})

        clear.assert_called_once_with("alice")

    def test_a_failure_is_a_generic_500(self, client):
        with patch.object(
            notification_routes.notification_service, "clear_all", side_effect=RuntimeError("secret detail")
        ):
            response = client.delete("/api/notifications")

        assert response.status_code == 500
        assert response.json()["ok"] is False
        assert "secret detail" not in response.text


async def _fake_stream(*_args, **_kwargs):
    yield "retry: 5000\n\n"
    yield 'event: notification\ndata: {"a":1}\n\n'


class TestStream:
    """The endpoint's wiring. The stream's own behaviour is in test_notification_stream.py.

    TestClient buffers a whole response before handing it back, so a real, endless stream
    would hang it; the generator is replaced with a finite one to let the wiring be checked.
    """

    def _get(self, cookie="live"):
        # No dependency override here: the real require_auth_no_slide must run.
        client = TestClient(create_app())
        client.cookies.set("dq_session", cookie)

        with patch.object(notification_routes, "notification_event_stream", _fake_stream), patch.object(
            notification_routes.notification_repository, "latest_id", return_value=42
        ) as latest_id:
            return client.get("/api/notifications/stream"), latest_id

    def test_streams_server_sent_events_with_buffering_switched_off(self):
        with patch.object(auth_service_module.session_repository, "peek", return_value="alice"):
            response, _ = self._get()

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        assert "no-cache" in response.headers["cache-control"]
        assert 'event: notification' in response.text

    def test_starts_from_the_users_latest_id_so_history_is_not_replayed(self):
        with patch.object(auth_service_module.session_repository, "peek", return_value="alice"):
            _, latest_id = self._get()

        latest_id.assert_called_once_with("alice")

    def test_authenticating_the_stream_does_not_slide_the_session(self):
        """The property the separate router exists for. get() extends the session's expiry;
        if the stream used it, an idle open tab would keep the session alive forever."""
        with patch.object(
            auth_service_module.session_repository, "peek", return_value="alice"
        ) as peek, patch.object(
            auth_service_module.session_repository, "get", side_effect=AssertionError("the stream slid the session")
        ) as get:
            response, _ = self._get()

        assert response.status_code == 200
        peek.assert_called_once()
        get.assert_not_called()

    def test_a_dead_session_is_a_401(self):
        with patch.object(auth_service_module.session_repository, "peek", return_value=None):
            response, _ = self._get(cookie="expired")

        assert response.status_code == 401

    def test_failing_to_start_is_a_clean_500_not_a_broken_stream(self):
        client = TestClient(create_app())
        client.cookies.set("dq_session", "live")

        with patch.object(auth_service_module.session_repository, "peek", return_value="alice"), patch.object(
            notification_routes.notification_repository, "latest_id", side_effect=RuntimeError("db down")
        ):
            response = client.get("/api/notifications/stream")

        assert response.status_code == 500
        assert response.json()["ok"] is False
