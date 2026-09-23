"""SessionRepository.peek: reads a session WITHOUT sliding its expiry.

The property under test is the whole reason peek exists. The notification stream
holds a connection open and re-checks its session; if that check slid the expiry
forward, an idle tab would keep the session alive indefinitely and the inactivity
timeout (SESSION_TTL_SECONDS) could never fire.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from repositories import session_repository as session_repository_module
from repositories.session_repository import SessionRepository


SESSIONS_DDL = """
CREATE TABLE sessions (
    session_id  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP
)
"""


def _naive_utc(delta: timedelta) -> datetime:
    return (datetime.now(timezone.utc) + delta).replace(tzinfo=None)


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )

    with engine.begin() as connection:
        connection.execute(text(SESSIONS_DDL))

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def repository(factory, monkeypatch):
    monkeypatch.setattr(session_repository_module, "get_db_session", factory)
    return SessionRepository(ttl_seconds=3600)


def _insert(factory, session_id, expires_in):
    with factory() as session:
        session.execute(
            text("INSERT INTO sessions (session_id, username, expires_at) VALUES (:i, 'alice', :e)"),
            {"i": session_id, "e": _naive_utc(expires_in)},
        )
        session.commit()


def _expiry(factory, session_id):
    with factory() as session:
        return session.execute(
            text("SELECT expires_at FROM sessions WHERE session_id = :i"), {"i": session_id}
        ).scalar()


def test_returns_the_username_for_a_live_session(repository, factory):
    _insert(factory, "s1", timedelta(minutes=5))

    assert repository.peek("s1") == "alice"


def test_does_not_slide_the_expiry_forward(repository, factory):
    """The contrast that matters: get() extends the session, peek() must not."""
    _insert(factory, "s1", timedelta(minutes=5))
    before = _expiry(factory, "s1")

    repository.peek("s1")

    assert _expiry(factory, "s1") == before

    repository.get("s1")

    assert _expiry(factory, "s1") != before, "sanity check: get() is the one that slides"


def test_an_expired_session_is_not_valid_and_is_left_in_place(repository, factory):
    _insert(factory, "old", timedelta(minutes=-5))

    assert repository.peek("old") is None
    assert _expiry(factory, "old") is not None, "peek is read-only; it does not delete"


@pytest.mark.parametrize("session_id", ["missing", "", None])
def test_unknown_or_empty_ids_are_not_valid(repository, session_id):
    assert repository.peek(session_id) is None


def test_fails_closed_when_the_database_is_unavailable(repository, monkeypatch):
    def boom():
        raise RuntimeError("database down")

    monkeypatch.setattr(session_repository_module, "get_db_session", boom)

    assert repository.peek("s1") is None
