"""The notification event stream, driven as a plain async generator.

The HTTP layer cannot be tested for this: Starlette's TestClient buffers a whole
response before returning it, so an endless stream would never come back. The
generator holds all the behaviour anyway - what it sends, when it pings, when it
gives up - and takes its collaborators as arguments, so it is exercised here with
a scripted repository and a tiny poll interval.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from services.notification_stream import RETRY_MILLISECONDS, format_event, notification_event_stream


def _row(nid):
    return {"id": nid, "type": "info", "title": f"n{nid}", "content": "", "status": "unread", "link": None, "created_at": "x"}


class FakeRepository:
    """Answers list_since from a script, one entry per poll; an Exception entry is raised."""

    def __init__(self, script, unread=1):
        self.script = list(script)
        self.unread = unread
        self.polls = []

    def list_since(self, username, after_id):
        self.polls.append((username, after_id))
        step = self.script.pop(0) if self.script else []

        if isinstance(step, Exception):
            raise step

        return step

    def unread_count(self, username):
        return self.unread


def _stream(repo, *, session_check=None, after_id=0, heartbeat=60.0):
    return notification_event_stream(
        "alice",
        "sid",
        after_id=after_id,
        poll_seconds=0.001,
        heartbeat_seconds=heartbeat,
        repository=repo,
        session_check=session_check or (lambda _sid: "alice"),
    )


async def _take(stream, count):
    frames = []

    async for frame in stream:
        frames.append(frame)

        if len(frames) >= count:
            break

    await stream.aclose()
    return frames


def _parse(frame):
    """Split one SSE frame into {field: value}."""
    return dict(line.split(": ", 1) for line in frame.strip().split("\n"))


def test_first_frame_tells_the_browser_how_long_to_wait_before_reconnecting():
    frames = asyncio.run(_take(_stream(FakeRepository([])), 1))

    assert frames == [f"retry: {RETRY_MILLISECONDS}\n\n"]


def test_new_notifications_are_sent_as_notification_events_with_the_unread_count():
    repo = FakeRepository([[_row(7)]], unread=4)

    frames = asyncio.run(_take(_stream(repo), 2))
    fields = _parse(frames[1])
    payload = json.loads(fields["data"])

    assert fields["event"] == "notification"
    assert fields["id"] == "7"
    assert payload["notification"]["id"] == 7
    assert payload["unread_count"] == 4


def test_a_batch_is_sent_oldest_first_and_the_cursor_moves_past_it():
    repo = FakeRepository([[_row(5), _row(6), _row(9)], []])

    frames = asyncio.run(_take(_stream(repo, after_id=4), 5))
    sent = [json.loads(_parse(f)["data"])["notification"]["id"] for f in frames[1:4]]

    assert sent == [5, 6, 9]
    # First poll starts from where the stream was opened, the next from the last id sent -
    # otherwise the same rows would be pushed again on every tick.
    assert repo.polls[0] == ("alice", 4)


def test_the_next_poll_asks_only_for_what_is_newer_than_the_last_id_sent():
    repo = FakeRepository([[_row(11)], [], []])

    async def run():
        stream = _stream(repo, after_id=10, heartbeat=0.005)
        await _take(stream, 3)  # retry, the event, then a heartbeat once it goes quiet

    asyncio.run(run())

    assert repo.polls[0][1] == 10
    assert repo.polls[1][1] == 11


def test_a_quiet_stream_sends_heartbeats_so_proxies_do_not_close_it():
    frames = asyncio.run(_take(_stream(FakeRepository([]), heartbeat=0.005), 3))

    assert frames[1] == ": ping\n\n"
    assert frames[2] == ": ping\n\n"


def test_a_failed_poll_does_not_end_the_stream_or_lose_the_cursor():
    """A database blip must not make every open tab reconnect at once."""
    repo = FakeRepository([RuntimeError("db blip"), [_row(3)]])

    frames = asyncio.run(_take(_stream(repo, after_id=2), 2))

    assert json.loads(_parse(frames[1])["data"])["notification"]["id"] == 3
    assert [p[1] for p in repo.polls[:2]] == [2, 2]


def test_the_stream_ends_when_the_session_is_no_longer_valid():
    """So it cannot quietly outlive a sign-out or an expired session."""
    checks = []

    def session_check(session_id):
        checks.append(session_id)
        return None  # signed out

    async def run():
        return [f async for f in _stream(FakeRepository([]), session_check=session_check, heartbeat=0.005)]

    frames = asyncio.run(asyncio.wait_for(run(), timeout=5))

    assert frames[0].startswith("retry:")
    assert checks == ["sid"]


def test_the_stream_ends_if_the_session_now_belongs_to_someone_else():
    async def run():
        return [f async for f in _stream(FakeRepository([]), session_check=lambda _s: "mallory", heartbeat=0.005)]

    frames = asyncio.run(asyncio.wait_for(run(), timeout=5))

    assert len(frames) == 1  # only the retry hint, then it stopped


def test_a_valid_session_keeps_the_stream_open():
    async def run():
        return await _take(_stream(FakeRepository([]), session_check=lambda _s: "alice", heartbeat=0.005), 4)

    assert len(asyncio.run(asyncio.wait_for(run(), timeout=5))) == 4


class TestFormatEvent:
    def test_shape(self):
        assert format_event("notification", {"a": 1}, event_id=3) == 'id: 3\nevent: notification\ndata: {"a":1}\n\n'

    def test_no_id_line_when_there_is_none(self):
        assert format_event("x", {}) == "event: x\ndata: {}\n\n"

    def test_a_newline_in_a_value_cannot_break_out_of_the_data_line(self):
        """SSE frames are newline-delimited, so a raw newline in a title would let it inject fields."""
        frame = format_event("notification", {"title": "a\n\nevent: evil\ndata: x"})

        assert frame.count("\n") == 3  # event line, data line, blank terminator
        assert json.loads(_parse(frame)["data"])["title"] == "a\n\nevent: evil\ndata: x"
