"""NotificationService: validation, and who may notify whom.

The repository is faked - its own tests cover the SQL - so these pin the rules the
service adds on top: what a valid notification is, that an in-app link cannot be
made to leave the app, and that only an admin can put a message in someone else's
bell.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services import notification_service as service_module
from services.notification_service import (
    MAX_CONTENT_LENGTH,
    MAX_PAGE_SIZE,
    MAX_TITLE_LENGTH,
    NotificationPermissionError,
    NotificationService,
    NotificationValidationError,
    is_internal_link,
)


@pytest.fixture
def repo():
    repo = MagicMock()
    repo.create.side_effect = lambda username, type_, title, content, link: {
        "id": 1, "type": type_, "title": title, "content": content, "link": link,
        "status": "unread", "username": username,
    }
    return repo


@pytest.fixture
def service(repo):
    return NotificationService(repository=repo)


@pytest.fixture
def is_admin():
    with patch.object(service_module.user_repository, "is_admin", return_value=False) as admin:
        yield admin


class TestIsInternalLink:
    @pytest.mark.parametrize("link", ["/", "/validator/abc", "/profile-mapper/1?tab=log", "/a#frag"])
    def test_accepts_in_app_paths(self, link):
        assert is_internal_link(link) is True

    @pytest.mark.parametrize(
        "link",
        [
            "https://evil.example",
            "http://evil.example/x",
            "//evil.example",            # protocol-relative: same origin rules as a full URL
            "/\\evil.example",           # browsers read a backslash as a slash -> "//evil.example"
            "javascript:alert(1)",
            "relative/path",
            "",
            "/\t/evil.example",          # browsers strip tabs/newlines from URLs -> "//evil.example"
            "/\n/evil.example",
            "/ok\x00",
        ],
    )
    def test_refuses_anything_that_could_leave_the_app(self, link):
        assert is_internal_link(link) is False


class TestCreateValidation:
    def test_a_minimal_notification_is_created_for_the_requester(self, service, repo, is_admin):
        result = service.create("alice", type="info", title="Hello")

        repo.create.assert_called_once_with("alice", "info", "Hello", "", None)
        assert result["title"] == "Hello"

    def test_text_is_stripped(self, service, repo, is_admin):
        service.create("alice", type="info", title="  Hi  ", content="  body ", link="  /home ")

        repo.create.assert_called_once_with("alice", "info", "Hi", "body", "/home")

    @pytest.mark.parametrize("bad_type", [None, "", "Job Done", "JOB", "1abc", "has-dash", "x" * 33, 5, ["a"]])
    def test_rejects_a_malformed_type(self, service, bad_type):
        with pytest.raises(NotificationValidationError, match="type"):
            service.create("alice", type=bad_type, title="t")

    @pytest.mark.parametrize("bad_title", [None, "", "   ", 5])
    def test_a_title_is_required(self, service, bad_title):
        with pytest.raises(NotificationValidationError, match="title"):
            service.create("alice", type="info", title=bad_title)

    def test_title_and_content_have_length_limits(self, service):
        with pytest.raises(NotificationValidationError, match="title"):
            service.create("alice", type="info", title="x" * (MAX_TITLE_LENGTH + 1))

        with pytest.raises(NotificationValidationError, match="content"):
            service.create("alice", type="info", title="t", content="x" * (MAX_CONTENT_LENGTH + 1))

    def test_content_must_be_a_string(self, service):
        with pytest.raises(NotificationValidationError, match="content"):
            service.create("alice", type="info", title="t", content={"a": 1})

    @pytest.mark.parametrize(
        "link", ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:x", "no-slash"]
    )
    def test_refuses_a_link_that_leaves_the_app(self, service, repo, link):
        with pytest.raises(NotificationValidationError, match="link"):
            service.create("alice", type="info", title="t", link=link)

        repo.create.assert_not_called()

    def test_a_blank_link_means_no_link(self, service, repo, is_admin):
        service.create("alice", type="info", title="t", link="   ")

        assert repo.create.call_args.args[4] is None


class TestWhoMayNotifyWhom:
    def test_a_user_may_notify_themselves_without_an_admin_lookup(self, service, repo, is_admin):
        service.create("alice", type="info", title="t", username="alice")

        repo.create.assert_called_once()
        is_admin.assert_not_called()

    def test_a_non_admin_cannot_notify_someone_else(self, service, repo, is_admin):
        """Otherwise any signed-in user could put a message, with a link, in anyone's bell."""
        is_admin.return_value = False

        with pytest.raises(NotificationPermissionError):
            service.create("alice", type="info", title="t", username="bob")

        repo.create.assert_not_called()

    def test_an_admin_may(self, service, repo, is_admin):
        is_admin.return_value = True

        service.create("alice", type="info", title="t", username="bob")

        assert repo.create.call_args.args[0] == "bob"
        is_admin.assert_called_once_with("alice")

    def test_the_target_defaults_to_the_requester_when_blank(self, service, repo, is_admin):
        service.create("alice", type="info", title="t", username="  ")

        assert repo.create.call_args.args[0] == "alice"


class TestListFor:
    def test_unread_count_comes_from_the_repository_not_from_the_page(self, service, repo):
        """A page can hold fewer rows than are unread; the badge must count them all."""
        repo.list_page.return_value = ([{"id": 9, "status": "unread"}], 9)
        repo.unread_count.return_value = 41

        result = service.list_for("alice", limit=1)

        assert result == {"items": [{"id": 9, "status": "unread"}], "unread_count": 41, "next_cursor": 9}

    @pytest.mark.parametrize("asked,used", [(0, 1), (-5, 1), (7, 7), (MAX_PAGE_SIZE, MAX_PAGE_SIZE), (10_000, MAX_PAGE_SIZE)])
    def test_the_page_size_is_clamped(self, service, repo, asked, used):
        repo.list_page.return_value = ([], None)
        repo.unread_count.return_value = 0

        service.list_for("alice", limit=asked)

        assert repo.list_page.call_args.args[1] == used

    def test_passes_the_cursor_and_filter_through(self, service, repo):
        repo.list_page.return_value = ([], None)
        repo.unread_count.return_value = 0

        service.list_for("alice", limit=5, before=42, unread_only=True)

        repo.list_page.assert_called_once_with("alice", 5, 42, True)


class TestMarkRead:
    def test_returns_the_notification_and_the_new_count(self, service, repo):
        repo.mark_read.return_value = {"id": 3, "status": "read"}
        repo.unread_count.return_value = 6

        assert service.mark_read("alice", 3) == {
            "notification": {"id": 3, "status": "read"},
            "unread_count": 6,
        }

    def test_not_found_is_none_and_skips_the_count(self, service, repo):
        repo.mark_read.return_value = None

        assert service.mark_read("alice", 3) is None
        repo.unread_count.assert_not_called()

    def test_mark_all_reports_how_many_and_the_remaining_count(self, service, repo):
        repo.mark_all_read.return_value = 4
        repo.unread_count.return_value = 0

        assert service.mark_all_read("alice") == {"updated": 4, "unread_count": 0}


class TestClearAll:
    def test_deletes_for_the_given_user_and_reports_how_many(self, service, repo):
        repo.delete_all.return_value = 12
        repo.unread_count.return_value = 0

        assert service.clear_all("alice") == {"deleted": 12, "unread_count": 0}
        repo.delete_all.assert_called_once_with("alice")

    def test_reads_the_unread_count_back_rather_than_assuming_zero(self, service, repo):
        """One can arrive between the delete and the count; the badge must reflect it."""
        repo.delete_all.return_value = 3
        repo.unread_count.return_value = 1

        assert service.clear_all("alice")["unread_count"] == 1
        repo.unread_count.assert_called_once_with("alice")
