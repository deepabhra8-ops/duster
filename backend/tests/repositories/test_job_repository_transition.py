"""JobRepository.transition against a real database, not a mock.

The whole point of this method is what SQL does when two writers race, so a
mock cannot test it - it would just return whatever it was told to. These run
the real ORM statement against an in-memory SQLite database.

The jobs table is created with explicit DDL rather than Base.metadata.create_all
because the model declares Postgres JSONB/UUID columns that SQLite has no
equivalent for. Only the columns transition() actually touches are needed, and
naming them here also documents exactly what it depends on.
"""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from repositories import job_repository as job_repository_module
from repositories.job_repository import JobRepository


JOBS_DDL = """
CREATE TABLE jobs (
    job_id           TEXT PRIMARY KEY,
    status           TEXT NOT NULL,
    glue_job_run_id  TEXT,
    started_at       TIMESTAMP,
    completed_at     TIMESTAMP,
    error_message    TEXT,
    step             TEXT
)
"""


@pytest.fixture
def session_factory(tmp_path):
    # A file-backed database, not ":memory:". An in-memory SQLite database is
    # private to the connection that opened it, so the worker threads in the
    # concurrency tests below would each get their own empty one and the race
    # under test would never actually happen.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    with engine.begin() as connection:
        connection.execute(text(JOBS_DDL))

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def repository(session_factory, monkeypatch):
    monkeypatch.setattr(job_repository_module, "get_db_session", session_factory)
    return JobRepository()


def _insert(session_factory, job_id="j1", status="draft"):
    with session_factory() as session:
        session.execute(
            text("INSERT INTO jobs (job_id, status) VALUES (:id, :status)"),
            {"id": job_id, "status": status},
        )
        session.commit()


def _status(session_factory, job_id="j1"):
    with session_factory() as session:
        return session.execute(
            text("SELECT status FROM jobs WHERE job_id = :id"), {"id": job_id}
        ).scalar()


class TestTransition:
    def test_a_valid_move_is_applied(self, repository, session_factory):
        _insert(session_factory, status="draft")

        assert repository.transition("j1", {"draft"}, "queued") is True
        assert _status(session_factory) == "queued"

    def test_a_move_from_the_wrong_state_changes_nothing(self, repository, session_factory):
        _insert(session_factory, status="running")

        assert repository.transition("j1", {"draft"}, "queued") is False
        assert _status(session_factory) == "running"

    def test_a_missing_job_is_reported_rather_than_raising(self, repository, session_factory):
        assert repository.transition("nope", {"draft"}, "queued") is False

    def test_several_source_states_are_accepted(self, repository, session_factory):
        _insert(session_factory, status="running")

        assert repository.transition("j1", {"queued", "running"}, "cancelling") is True
        assert _status(session_factory) == "cancelling"

    def test_extra_fields_are_written_alongside_the_status(self, repository, session_factory):
        _insert(session_factory, status="running")

        repository.transition("j1", {"running"}, "error", error="it broke")

        with session_factory() as session:
            message = session.execute(
                text("SELECT error_message FROM jobs WHERE job_id = 'j1'")
            ).scalar()

        # 'error' is mapped onto the error_message column.
        assert message == "it broke"

    def test_an_unknown_field_is_ignored_rather_than_raising(self, repository, session_factory):
        _insert(session_factory, status="running")

        assert repository.transition("j1", {"running"}, "done", not_a_column="x") is True


class TestTerminalStatesAreProtected:
    @pytest.mark.parametrize("terminal", ["done", "error", "cancelled"])
    def test_a_finished_job_is_not_reopened(self, repository, session_factory, terminal):
        """Both the request thread and the background job-runner thread write
        this row. Without the status guard a late write could resurrect a job
        that had already finished or been cancelled."""
        _insert(session_factory, status=terminal)

        assert repository.transition("j1", {"queued", "running"}, "done") is False
        assert _status(session_factory) == terminal


class TestConcurrency:
    def test_only_one_of_many_racing_callers_wins(self, repository, session_factory):
        """The reason this method exists. Ten threads ask to move the same draft
        to queued; exactly one may be told it did."""
        _insert(session_factory, status="draft")

        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(10, timeout=10)

        def attempt():
            barrier.wait()
            won = repository.transition("j1", {"draft"}, "queued")
            with lock:
                results.append(won)

        threads = [threading.Thread(target=attempt) for _ in range(10)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert results.count(True) == 1, f"expected exactly one winner, got {results}"
        assert _status(session_factory) == "queued"

    def test_racing_transitions_to_different_states_produce_one_outcome(
        self, repository, session_factory
    ):
        """A cancel and a completion arriving together must not both apply."""
        _insert(session_factory, status="running")

        results = {}
        barrier = threading.Barrier(2, timeout=10)

        def attempt(name, target):
            barrier.wait()
            results[name] = repository.transition("j1", {"running"}, target)

        threads = [
            threading.Thread(target=attempt, args=("done", "done")),
            threading.Thread(target=attempt, args=("cancel", "cancelling")),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert sum(results.values()) == 1
        assert _status(session_factory) in {"done", "cancelling"}
