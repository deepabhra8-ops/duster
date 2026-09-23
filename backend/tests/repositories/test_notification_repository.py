"""NotificationRepository against a real database, not a mock.

What matters here is what SQL does - which rows a query returns, and for whom - so a
mock would only echo back whatever it was told to. These run the real ORM statements
against a file-backed SQLite database.

The table is created with explicit DDL rather than Base.metadata.create_all, as in
test_job_repository_transition.py: the models file declares Postgres-only column
types elsewhere, and naming the columns here documents exactly what the repository
depends on. The Postgres side (CHECK constraints, the job-finished trigger) is
migration 008's and is not something SQLite can stand in for.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from repositories import notification_repository as repository_module
from repositories.models import Notification
from repositories.notification_repository import NotificationRepository


NOTIFICATIONS_DDL = """
CREATE TABLE notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT      NOT NULL,
    type        TEXT      NOT NULL,
    title       TEXT      NOT NULL,
    content     TEXT      NOT NULL DEFAULT '',
    status      TEXT      NOT NULL DEFAULT 'unread',
    link        TEXT,
    created_at  TIMESTAMP NOT NULL
)
"""


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    with engine.begin() as connection:
        connection.execute(text(NOTIFICATIONS_DDL))

    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def repository(session_factory, monkeypatch):
    monkeypatch.setattr(repository_module, "get_db_session", session_factory)
    return NotificationRepository()


def _add(repository, username="alice", n=1):
    """Create `n` notifications and return their ids, oldest first."""
    return [repository.create(username, "info", f"title {i}")["id"] for i in range(n)]


class TestCreate:
    def test_returns_the_stored_notification_unread(self, repository):
        created = repository.create("alice", "job_done", "Done", "It finished", "/validator/abc")

        assert created["id"] > 0
        assert created["type"] == "job_done"
        assert created["title"] == "Done"
        assert created["content"] == "It finished"
        assert created["link"] == "/validator/abc"
        assert created["status"] == "unread"

    def test_timestamp_carries_an_explicit_utc_offset(self, repository):
        """Stored naive, but a bare ISO string is read by browsers as LOCAL time, which
        makes every "5 minutes ago" wrong by the viewer's UTC offset."""
        created = repository.create("alice", "info", "t")

        stamp = datetime.fromisoformat(created["created_at"])

        assert stamp.tzinfo is not None
        assert stamp.utcoffset() == timedelta(0)
        assert abs(datetime.now(timezone.utc) - stamp) < timedelta(seconds=30)

    def test_content_and_link_are_optional(self, repository):
        created = repository.create("alice", "info", "t")

        assert created["content"] == ""
        assert created["link"] is None


class TestListPage:
    def test_newest_first(self, repository):
        ids = _add(repository, n=3)

        items, _ = repository.list_page("alice", limit=10)

        assert [i["id"] for i in items] == list(reversed(ids))

    def test_pages_walk_the_whole_list_with_no_gap_or_repeat(self, repository):
        ids = _add(repository, n=5)

        seen, cursor = [], None
        while True:
            items, cursor = repository.list_page("alice", limit=2, before_id=cursor)
            seen += [i["id"] for i in items]
            if cursor is None:
                break

        assert seen == list(reversed(ids))

    def test_a_row_arriving_between_pages_does_not_shift_the_next_page(self, repository):
        """The reason this is keyset- and not offset-paged: the list is live. With OFFSET, a
        new row would push everything down one and the seam row would be served twice."""
        ids = _add(repository, n=4)

        first, cursor = repository.list_page("alice", limit=2)
        _add(repository, n=1)  # a notification arrives while the user is scrolling
        second, _ = repository.list_page("alice", limit=2, before_id=cursor)

        assert [i["id"] for i in first + second] == list(reversed(ids))

    def test_last_page_has_no_cursor_and_a_full_page_does_not_invent_one(self, repository):
        _add(repository, n=4)

        _, cursor_when_more = repository.list_page("alice", limit=3)
        _, cursor_when_exact = repository.list_page("alice", limit=4)

        assert cursor_when_more is not None
        assert cursor_when_exact is None

    def test_unread_only_filters(self, repository):
        ids = _add(repository, n=3)
        repository.mark_read("alice", ids[1])

        items, _ = repository.list_page("alice", limit=10, unread_only=True)

        assert sorted(i["id"] for i in items) == [ids[0], ids[2]]

    def test_never_returns_another_users_notifications(self, repository):
        _add(repository, "alice", n=2)
        _add(repository, "bob", n=3)

        items, _ = repository.list_page("alice", limit=10)

        assert len(items) == 2

    def test_empty_list(self, repository):
        assert repository.list_page("alice", limit=10) == ([], None)


class TestUnreadCount:
    def test_counts_only_this_users_unread(self, repository):
        mine = _add(repository, "alice", n=3)
        _add(repository, "bob", n=5)
        repository.mark_read("alice", mine[0])

        assert repository.unread_count("alice") == 2
        assert repository.unread_count("bob") == 5

    def test_zero_for_a_user_with_nothing(self, repository):
        assert repository.unread_count("nobody") == 0

    def test_counts_beyond_a_single_page(self, repository):
        """The badge is the whole unread total, not the number of rows a page holds."""
        _add(repository, n=7)

        items, _ = repository.list_page("alice", limit=2)

        assert len(items) == 2
        assert repository.unread_count("alice") == 7


class TestMarkRead:
    def test_marks_it_read_and_returns_it(self, repository):
        (nid,) = _add(repository, n=1)

        result = repository.mark_read("alice", nid)

        assert result["id"] == nid
        assert result["status"] == "read"
        assert repository.unread_count("alice") == 0

    def test_is_idempotent(self, repository):
        (nid,) = _add(repository, n=1)

        repository.mark_read("alice", nid)
        again = repository.mark_read("alice", nid)

        assert again is not None
        assert again["status"] == "read"

    def test_someone_elses_notification_is_indistinguishable_from_a_missing_one(self, repository):
        (bobs,) = _add(repository, "bob", n=1)

        assert repository.mark_read("alice", bobs) is None
        assert repository.mark_read("alice", 99999) is None
        # ...and it was not touched.
        assert repository.unread_count("bob") == 1

    def test_leaves_the_others_alone(self, repository):
        ids = _add(repository, n=3)

        repository.mark_read("alice", ids[0])

        assert repository.unread_count("alice") == 2


class TestMarkAllRead:
    def test_marks_only_this_users_and_reports_how_many(self, repository):
        _add(repository, "alice", n=3)
        _add(repository, "bob", n=2)

        changed = repository.mark_all_read("alice")

        assert changed == 3
        assert repository.unread_count("alice") == 0
        assert repository.unread_count("bob") == 2

    def test_reports_zero_when_nothing_was_unread(self, repository):
        _add(repository, n=2)
        repository.mark_all_read("alice")

        assert repository.mark_all_read("alice") == 0


class TestDeleteAll:
    def test_removes_every_notification_of_that_user_read_or_not(self, repository):
        ids = _add(repository, "alice", n=4)
        repository.mark_read("alice", ids[0])

        deleted = repository.delete_all("alice")

        assert deleted == 4
        assert repository.list_page("alice", limit=50) == ([], None)
        assert repository.unread_count("alice") == 0

    def test_never_touches_another_users_notifications(self, repository):
        """The property that matters: the caller can only ever clear their own."""
        _add(repository, "alice", n=3)
        bobs = _add(repository, "bob", n=2)
        repository.mark_read("bob", bobs[0])

        repository.delete_all("alice")

        items, _ = repository.list_page("bob", limit=50)
        assert sorted(i["id"] for i in items) == sorted(bobs)
        assert repository.unread_count("bob") == 1  # bob's read/unread state is untouched too

    def test_is_idempotent_and_reports_zero_when_there_was_nothing(self, repository):
        _add(repository, "alice", n=2)

        assert repository.delete_all("alice") == 2
        assert repository.delete_all("alice") == 0
        assert repository.delete_all("nobody") == 0

    def test_new_notifications_after_clearing_are_kept_and_still_ordered(self, repository):
        """Ids are never reused, so the live stream's cursor stays valid across a clear."""
        old = _add(repository, "alice", n=2)
        repository.delete_all("alice")

        new = _add(repository, "alice", n=1)

        assert new[0] > max(old)
        assert [i["id"] for i in repository.list_page("alice", limit=10)[0]] == new
        assert repository.latest_id("alice") == new[0]


# A fixed "now" so every age below is exact, and a 7-day window.
NOW = datetime(2026, 9, 21, 12, 0, 0)
CUTOFF = NOW - timedelta(days=7)


def _seed(session_factory, username, status, age_days):
    """Insert one notification created `age_days` before NOW and return its id.

    Through the ORM model, not raw SQL, so the timestamp is stored in exactly the format the
    query later compares it in - otherwise the "exactly at the cutoff" case would be decided by
    string formatting rather than by the logic under test.
    """
    with session_factory() as session:
        row = Notification(
            username=username,
            type="info",
            title="t",
            status=status,
            created_at=NOW - timedelta(days=age_days),
        )
        session.add(row)
        session.commit()
        return row.id


def _remaining(session_factory):
    with session_factory() as session:
        return [row[0] for row in session.execute(text("SELECT id FROM notifications ORDER BY id"))]


class TestPurgeRead:
    def test_deletes_read_notifications_older_than_the_cutoff(self, repository, session_factory):
        old_read = _seed(session_factory, "alice", "read", age_days=8)

        assert repository.purge_read_before(CUTOFF) == 1
        assert old_read not in _remaining(session_factory)

    def test_keeps_read_notifications_that_are_still_inside_the_window(self, repository, session_factory):
        fresh_read = _seed(session_factory, "alice", "read", age_days=6)

        assert repository.purge_read_before(CUTOFF) == 0
        assert _remaining(session_factory) == [fresh_read]

    def test_never_deletes_an_unread_notification_however_old(self, repository, session_factory):
        """Only the status column decides. A year-old unread notification is still news."""
        ancient_unread = _seed(session_factory, "alice", "unread", age_days=365)

        assert repository.purge_read_before(CUTOFF) == 0
        assert _remaining(session_factory) == [ancient_unread]

    def test_one_created_exactly_at_the_cutoff_is_kept(self, repository, session_factory):
        """Strictly older than the window, not "at least as old"."""
        on_the_line = _seed(session_factory, "alice", "read", age_days=7)

        assert repository.purge_read_before(CUTOFF) == 0
        assert _remaining(session_factory) == [on_the_line]

    def test_applies_to_every_users_own_read_notifications_and_only_those(self, repository, session_factory):
        alice_old_read = _seed(session_factory, "alice", "read", age_days=10)
        alice_old_unread = _seed(session_factory, "alice", "unread", age_days=10)
        bob_old_read = _seed(session_factory, "bob", "read", age_days=9)
        bob_fresh_read = _seed(session_factory, "bob", "read", age_days=1)

        deleted = repository.purge_read_before(CUTOFF)

        assert deleted == 2
        assert _remaining(session_factory) == [alice_old_unread, bob_fresh_read]
        assert alice_old_read not in _remaining(session_factory)
        assert bob_old_read not in _remaining(session_factory)

    def test_the_age_counts_from_creation_not_from_when_it_was_read(self, repository, session_factory):
        """The stated requirement, and its consequence: a notification that sat unread past the
        window is deleted at the next sweep after it is finally opened."""
        stale = _seed(session_factory, "alice", "unread", age_days=8)
        assert repository.purge_read_before(CUTOFF) == 0  # unread: safe

        repository.mark_read("alice", stale)

        assert repository.purge_read_before(CUTOFF) == 1
        assert _remaining(session_factory) == []

    def test_reports_zero_on_an_empty_table(self, repository):
        assert repository.purge_read_before(CUTOFF) == 0

    def test_works_through_a_backlog_in_batches(self, repository, session_factory):
        for _ in range(7):
            _seed(session_factory, "alice", "read", age_days=20)
        keeper = _seed(session_factory, "alice", "read", age_days=1)

        deleted = repository.purge_read_before(CUTOFF, batch_size=3)

        assert deleted == 7  # three batches: 3 + 3 + 1
        assert _remaining(session_factory) == [keeper]

    def test_a_backlog_that_is_an_exact_multiple_of_the_batch_size_still_terminates(self, repository, session_factory):
        for _ in range(6):
            _seed(session_factory, "alice", "read", age_days=20)

        assert repository.purge_read_before(CUTOFF, batch_size=3) == 6
        assert _remaining(session_factory) == []

    def test_one_call_is_bounded_and_the_next_finishes_the_job(self, repository, session_factory):
        """A big backlog is worked off across sweeps, not in one long, lock-holding run."""
        for _ in range(7):
            _seed(session_factory, "alice", "read", age_days=20)

        assert repository.purge_read_before(CUTOFF, batch_size=3, max_batches=2) == 6
        assert len(_remaining(session_factory)) == 1

        assert repository.purge_read_before(CUTOFF, batch_size=3, max_batches=2) == 1
        assert _remaining(session_factory) == []


class TestStreamHelpers:
    def test_latest_id_is_zero_with_no_rows_and_per_user(self, repository):
        assert repository.latest_id("alice") == 0

        _add(repository, "alice", n=2)
        (bobs,) = _add(repository, "bob", n=1)

        assert repository.latest_id("bob") == bobs
        assert repository.latest_id("alice") < bobs

    def test_list_since_returns_only_newer_rows_oldest_first(self, repository):
        ids = _add(repository, n=4)

        rows = repository.list_since("alice", after_id=ids[1])

        assert [r["id"] for r in rows] == [ids[2], ids[3]]

    def test_list_since_is_per_user_and_honours_its_limit(self, repository):
        _add(repository, "bob", n=3)
        ids = _add(repository, "alice", n=5)

        rows = repository.list_since("alice", after_id=0, limit=2)

        assert [r["id"] for r in rows] == ids[:2]

    def test_nothing_newer_is_an_empty_list(self, repository):
        (nid,) = _add(repository, n=1)

        assert repository.list_since("alice", after_id=nid) == []
