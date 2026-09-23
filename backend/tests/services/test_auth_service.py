"""Unit tests for AuthService.login - credential verification and legacy upgrade.

Both repositories are patched throughout; no database is touched.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services.auth_service import AuthService
from common.security.password_hash import hash_password


PASSWORD = "hunter2"


def _user(password_hash: str, is_active: bool = True, expiry_date=None) -> dict:
    return {
        "username": "alice",
        "password_hash": password_hash,
        "is_active": is_active,
        "expiry_date": expiry_date,
    }


@pytest.fixture
def service():
    return AuthService()


@pytest.fixture
def repos():
    with patch("services.auth_service.user_repository") as users, patch(
        "services.auth_service.session_repository"
    ) as sessions:
        sessions.create.return_value = "session-abc"
        yield users, sessions


class TestSuccessfulLogin:
    def test_tagged_hash_logs_in_without_rewriting(self, service, repos):
        users, sessions = repos
        users.get_by_username.return_value = _user(hash_password(PASSWORD))

        assert service.login("alice", PASSWORD) == "session-abc"
        sessions.create.assert_called_once_with("alice")
        users.set_password.assert_not_called()

    def test_username_is_trimmed(self, service, repos):
        users, _ = repos
        users.get_by_username.return_value = _user(hash_password(PASSWORD))

        service.login("  alice  ", PASSWORD)

        users.get_by_username.assert_called_once_with("alice")


class TestLegacyUpgrade:
    def test_plaintext_row_is_rewritten_as_a_hash(self, service, repos):
        users, _ = repos
        users.get_by_username.return_value = _user(PASSWORD)  # stored plaintext

        assert service.login("alice", PASSWORD) == "session-abc"
        users.set_password.assert_called_once_with("alice", PASSWORD)

    def test_bare_digest_row_is_rewritten_as_a_tagged_hash(self, service, repos):
        users, _ = repos
        bare = hashlib.sha256(PASSWORD.encode()).hexdigest()
        users.get_by_username.return_value = _user(bare)

        assert service.login("alice", PASSWORD) == "session-abc"
        users.set_password.assert_called_once_with("alice", PASSWORD)

    def test_a_failed_upgrade_does_not_fail_the_login(self, service, repos):
        users, _ = repos
        users.get_by_username.return_value = _user(PASSWORD)
        users.set_password.side_effect = RuntimeError("database is down")

        # The password was correct; a write problem afterwards is operational,
        # not an authentication decision.
        assert service.login("alice", PASSWORD) == "session-abc"

    def test_wrong_password_never_triggers_an_upgrade(self, service, repos):
        users, _ = repos
        users.get_by_username.return_value = _user(PASSWORD)

        assert service.login("alice", "wrong") is None
        users.set_password.assert_not_called()


class TestRejection:
    def test_unknown_user(self, service, repos):
        users, sessions = repos
        users.get_by_username.return_value = None

        assert service.login("nobody", PASSWORD) is None
        sessions.create.assert_not_called()

    def test_wrong_password(self, service, repos):
        users, sessions = repos
        users.get_by_username.return_value = _user(hash_password(PASSWORD))

        assert service.login("alice", "wrong") is None
        sessions.create.assert_not_called()

    def test_inactive_account(self, service, repos):
        users, sessions = repos
        users.get_by_username.return_value = _user(hash_password(PASSWORD), is_active=False)

        assert service.login("alice", PASSWORD) is None
        sessions.create.assert_not_called()

    def test_expired_account(self, service, repos):
        users, sessions = repos
        expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        users.get_by_username.return_value = _user(hash_password(PASSWORD), expiry_date=expired)

        assert service.login("alice", PASSWORD) is None
        sessions.create.assert_not_called()

    def test_future_expiry_is_allowed(self, service, repos):
        users, _ = repos
        future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        users.get_by_username.return_value = _user(hash_password(PASSWORD), expiry_date=future)

        assert service.login("alice", PASSWORD) == "session-abc"

    @pytest.mark.parametrize("username,password", [("", PASSWORD), ("alice", ""), ("", "")])
    def test_empty_credentials_short_circuit(self, service, repos, username, password):
        users, _ = repos

        assert service.login(username, password) is None
        users.get_by_username.assert_not_called()

    def test_null_stored_password_is_rejected(self, service, repos):
        users, sessions = repos
        users.get_by_username.return_value = _user(None)

        assert service.login("alice", PASSWORD) is None
        sessions.create.assert_not_called()
