import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api/api.js";
import { useNotifications } from "../hooks/useNotifications.js";
import { FakeEventSource } from "../test/fakeEventSource.js";
import { ToastProvider } from "./ToastContext.jsx";
import {
  initialNotificationsState,
  NotificationsProvider,
  notificationsReducer as reduce,
} from "./NotificationsContext.jsx";

vi.mock("../api/api.js", () => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  clearAllNotifications: vi.fn(),
  notificationStreamUrl: () => "http://test/api/notifications/stream",
}));

const n = (id, over = {}) => ({
  id,
  type: "job_done",
  title: `Title ${id}`,
  content: `Body ${id}`,
  status: "unread",
  link: `/validator/${id}`,
  created_at: "2026-09-21T10:00:00+00:00",
  ...over,
});

const page = (items, { unread = items.filter((i) => i.status === "unread").length, next = null } = {}) => ({
  ok: true,
  data: { ok: true, data: { items, unread_count: unread, next_cursor: next } },
});

const read = (notification, unread) => ({
  ok: true,
  data: { ok: true, data: { notification: { ...notification, status: "read" }, unread_count: unread } },
});

const loaded = (over = {}) => ({ ...initialNotificationsState, loaded: true, status: "ready", ...over });

describe("reducer: refreshed (a fetched first page)", () => {
  it("fills an empty state and adopts the server's cursor and total", () => {
    const state = reduce(initialNotificationsState, {
      type: "refreshed",
      items: [n(3), n(2)],
      unreadCount: 40,
      nextCursor: 2,
    });

    expect(state.items.map((i) => i.id)).toEqual([3, 2]);
    expect(state.unreadCount).toBe(40);
    expect(state.nextCursor).toBe(2);
    expect(state.loaded).toBe(true);
    expect(state.status).toBe("ready");
  });

  it("keeps the older pages already scrolled through, and the cursor into them", () => {
    const held = loaded({ items: [n(9), n(8), n(7), n(6), n(5)], nextCursor: 5, unreadCount: 5 });

    const next = reduce(held, { type: "refreshed", items: [n(9), n(8)], unreadCount: 5, nextCursor: 8 });

    expect(next.items.map((i) => i.id)).toEqual([9, 8, 7, 6, 5]);
    expect(next.nextCursor).toBe(5);
  });

  it("takes the newer copy of a row it already holds (it may have been read elsewhere)", () => {
    const held = loaded({ items: [n(2), n(1)], unreadCount: 2 });

    const next = reduce(held, {
      type: "refreshed",
      items: [n(2, { status: "read" }), n(1)],
      unreadCount: 1,
      nextCursor: null,
    });

    expect(next.items.find((i) => i.id === 2).status).toBe("read");
    expect(next.unreadCount).toBe(1);
  });

  it("adds notifications that arrived since, in front", () => {
    const held = loaded({ items: [n(2), n(1)] });

    const next = reduce(held, { type: "refreshed", items: [n(4), n(3), n(2)], unreadCount: 4, nextCursor: 2 });

    expect(next.items.map((i) => i.id)).toEqual([4, 3, 2, 1]);
  });

  it("drops the held list when more than a page arrived, rather than hide the hole", () => {
    const held = loaded({ items: [n(3), n(2), n(1)], nextCursor: null });
    const fresh = Array.from({ length: 20 }, (_, i) => n(30 - i));

    const next = reduce(held, { type: "refreshed", items: fresh, unreadCount: 30, nextCursor: 11 });

    expect(next.items.map((i) => i.id)).toEqual(fresh.map((i) => i.id));
    expect(next.nextCursor).toBe(11);
  });

  it("an empty page really is empty", () => {
    const held = loaded({ items: [n(2), n(1)], unreadCount: 2, nextCursor: 1 });

    const next = reduce(held, { type: "refreshed", items: [], unreadCount: 0, nextCursor: null });

    expect(next.items).toEqual([]);
    expect(next.nextCursor).toBeNull();
    expect(next.unreadCount).toBe(0);
  });

  it("does not trust a cursor from a state that never loaded (a push can beat the first fetch)", () => {
    const pushedFirst = { ...initialNotificationsState, items: [n(50)], nextCursor: null };

    const next = reduce(pushedFirst, { type: "refreshed", items: [n(50), n(49)], unreadCount: 2, nextCursor: 49 });

    expect(next.nextCursor).toBe(49);
  });

  it("clears a previous error", () => {
    const next = reduce(loaded({ error: "boom" }), { type: "refreshed", items: [], unreadCount: 0, nextCursor: null });

    expect(next.error).toBe("");
  });
});

describe("reducer: refreshFailed", () => {
  it("leaves the list alone and records the error", () => {
    const held = loaded({ items: [n(1)], unreadCount: 1 });

    const next = reduce(held, { type: "refreshFailed", error: "HTTP 500" });

    expect(next.items).toEqual(held.items);
    expect(next.error).toBe("HTTP 500");
  });

  it("ends the initial 'loading' state, so the panel can show the error instead of a spinner", () => {
    expect(reduce(initialNotificationsState, { type: "refreshFailed", error: "x" }).status).toBe("ready");
  });
});

describe("reducer: received (a live push)", () => {
  it("puts it first and takes the count the server sent", () => {
    const next = reduce(loaded({ items: [n(2)], unreadCount: 1 }), {
      type: "received",
      notification: n(3),
      unreadCount: 7,
    });

    expect(next.items.map((i) => i.id)).toEqual([3, 2]);
    expect(next.unreadCount).toBe(7);
  });

  it("does not list one it already holds, but still takes the fresher count", () => {
    const next = reduce(loaded({ items: [n(3), n(2)], unreadCount: 2 }), {
      type: "received",
      notification: n(3),
      unreadCount: 5,
    });

    expect(next.items).toHaveLength(2);
    expect(next.unreadCount).toBe(5);
  });

  it("keeps the list ordered even if one commits out of order", () => {
    const next = reduce(loaded({ items: [n(9), n(7)] }), { type: "received", notification: n(8), unreadCount: 3 });

    expect(next.items.map((i) => i.id)).toEqual([9, 8, 7]);
  });

  it("falls back to counting it if the server sent no total", () => {
    const next = reduce(loaded({ unreadCount: 4 }), { type: "received", notification: n(1) });

    expect(next.unreadCount).toBe(5);
  });
});

describe("reducer: marking read", () => {
  it("flips the row and lowers the count by one", () => {
    const next = reduce(loaded({ items: [n(2), n(1)], unreadCount: 9 }), { type: "markedReadLocal", id: 2 });

    expect(next.items.find((i) => i.id === 2).status).toBe("read");
    expect(next.unreadCount).toBe(8);
  });

  it("does nothing for a row already read, or one it does not hold", () => {
    const held = loaded({ items: [n(2, { status: "read" })], unreadCount: 3 });

    expect(reduce(held, { type: "markedReadLocal", id: 2 })).toBe(held);
    expect(reduce(held, { type: "markedReadLocal", id: 99 })).toBe(held);
  });

  it("never takes the count below zero", () => {
    const next = reduce(loaded({ items: [n(1)], unreadCount: 0 }), { type: "markedReadLocal", id: 1 });

    expect(next.unreadCount).toBe(0);
  });

  it("undoes itself when the server refuses", () => {
    const held = loaded({ items: [n(2), n(1)], unreadCount: 2 });
    const undone = reduce(reduce(held, { type: "markedReadLocal", id: 2 }), { type: "markReadReverted", id: 2 });

    expect(undone.items.find((i) => i.id === 2).status).toBe("unread");
    expect(undone.unreadCount).toBe(2);
  });

  it("does not 'undo' a row that was never marked", () => {
    const held = loaded({ items: [n(1)], unreadCount: 1 });

    expect(reduce(held, { type: "markReadReverted", id: 1 })).toBe(held);
  });

  it("marks every loaded row read and zeroes the count", () => {
    const next = reduce(loaded({ items: [n(2), n(1, { status: "read" })], unreadCount: 12 }), {
      type: "allMarkedReadLocal",
    });

    expect(next.items.every((i) => i.status === "read")).toBe(true);
    expect(next.unreadCount).toBe(0);
  });

  it("clearing empties the list, the count AND the cursor (unloaded pages are deleted too)", () => {
    const held = loaded({ items: [n(9), n(8)], unreadCount: 40, nextCursor: 8, error: "old" });

    const next = reduce(held, { type: "allClearedLocal" });

    expect(next.items).toEqual([]);
    expect(next.unreadCount).toBe(0);
    expect(next.nextCursor).toBeNull();
    expect(next.error).toBe("");
    expect(next.loaded).toBe(true);
  });

  it("a page fetched after clearing replaces the (empty) list rather than merging into it", () => {
    const cleared = reduce(loaded({ items: [n(9), n(8)], nextCursor: 8 }), { type: "allClearedLocal" });

    const next = reduce(cleared, { type: "refreshed", items: [n(12), n(11)], unreadCount: 2, nextCursor: null });

    expect(next.items.map((i) => i.id)).toEqual([12, 11]);
  });

  it("countSynced sets the count from the server", () => {
    expect(reduce(loaded({ unreadCount: 8 }), { type: "countSynced", unreadCount: 2 }).unreadCount).toBe(2);
  });
});

describe("reducer: paging", () => {
  it("appends the next page, drops repeats, and takes the new cursor", () => {
    const next = reduce(loaded({ items: [n(5), n(4)], nextCursor: 4, loadingMore: true }), {
      type: "loadedMore",
      items: [n(4), n(3)],
      nextCursor: null,
    });

    expect(next.items.map((i) => i.id)).toEqual([5, 4, 3]);
    expect(next.nextCursor).toBeNull();
    expect(next.loadingMore).toBe(false);
  });

  it("a failed page load stops the spinner and reports it, keeping the cursor to retry with", () => {
    const next = reduce(loaded({ nextCursor: 4, loadingMore: true }), { type: "loadMoreFailed", error: "nope" });

    expect(next.loadingMore).toBe(false);
    expect(next.error).toBe("nope");
    expect(next.nextCursor).toBe(4);
  });
});

let ctx;

function Probe() {
  ctx = useNotifications();

  return (
    <div>
      <span data-testid="count">{ctx.unreadCount}</span>
      <span data-testid="ids">{ctx.items.map((i) => i.id).join(",")}</span>
      <span data-testid="statuses">{ctx.items.map((i) => `${i.id}:${i.status}`).join(",")}</span>
      <span data-testid="status">{ctx.status}</span>
      <span data-testid="more">{String(ctx.hasMore)}</span>
      <span data-testid="error">{ctx.error}</span>
    </div>
  );
}

function mount() {
  return render(
    <ToastProvider>
      <NotificationsProvider>
        <Probe />
      </NotificationsProvider>
    </ToastProvider>
  );
}

const text = (id) => screen.getByTestId(id).textContent;
const ready = () => waitFor(() => expect(text("status")).toBe("ready"));

const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });

beforeEach(() => {
  vi.resetAllMocks();
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
  api.listNotifications.mockResolvedValue(page([]));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("provider: loading", () => {
  it("loads the first page on mount and shows the server's total, not the page's", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2, { status: "read" }), n(1)], { unread: 42, next: 1 }));

    mount();
    await ready();

    expect(api.listNotifications).toHaveBeenCalledWith({ limit: 20 });
    expect(text("ids")).toBe("3,2,1");
    expect(text("count")).toBe("42");
    expect(text("more")).toBe("true");
  });

  it("reports a failed first load instead of staying on 'loading'", async () => {
    api.listNotifications.mockResolvedValue({ ok: false, error: "HTTP 500" });

    mount();
    await ready();

    expect(text("error")).toBe("HTTP 500");
    expect(text("ids")).toBe("");
  });

  it("still works where the browser has no EventSource - just not live", async () => {
    vi.stubGlobal("EventSource", undefined);
    api.listNotifications.mockResolvedValue(page([n(1)]));

    mount();
    await ready();

    expect(text("ids")).toBe("1");
  });

  it("a slow, older refresh cannot overwrite a newer one", async () => {
    let resolveSlow;
    api.listNotifications
      .mockReturnValueOnce(new Promise((resolve) => { resolveSlow = resolve; }))
      .mockResolvedValueOnce(page([n(2)], { unread: 1 }));

    mount();
    await act(async () => FakeEventSource.last.open());
    await waitFor(() => expect(text("ids")).toBe("2"));

    await act(async () => resolveSlow(page([n(1)], { unread: 9 })));

    expect(text("ids")).toBe("2");
    expect(text("count")).toBe("1");
  });
});

describe("provider: the live stream", () => {
  it("connects with the session cookie", async () => {
    mount();
    await ready();

    expect(FakeEventSource.last.url).toBe("http://test/api/notifications/stream");
    expect(FakeEventSource.last.options).toEqual({ withCredentials: true });
  });

  it("refetches whenever it opens, which is what makes 'start from now' lossless", async () => {
    mount();
    await ready();
    expect(api.listNotifications).toHaveBeenCalledTimes(1);

    await act(async () => FakeEventSource.last.open());

    expect(api.listNotifications).toHaveBeenCalledTimes(2);
  });

  it("puts a pushed notification first and raises the badge", async () => {
    api.listNotifications.mockResolvedValue(page([n(2), n(1)], { unread: 2 }));
    mount();
    await ready();

    act(() => FakeEventSource.last.emit("notification", { notification: n(3), unread_count: 3 }));

    expect(text("ids")).toBe("3,2,1");
    expect(text("count")).toBe("3");
  });

  it("does not double-count a notification the list request and the stream both delivered", async () => {
    api.listNotifications.mockResolvedValue(page([n(2), n(1)], { unread: 2 }));
    mount();
    await ready();

    act(() => FakeEventSource.last.emit("notification", { notification: n(2), unread_count: 2 }));

    expect(text("ids")).toBe("2,1");
    expect(text("count")).toBe("2");
  });

  it("survives a frame it cannot read", async () => {
    mount();
    await ready();

    act(() => FakeEventSource.last.emit("notification", "{not json"));

    expect(text("status")).toBe("ready");
  });

  it("leaves a dropped connection to the browser, which retries by itself", async () => {
    mount();
    await ready();

    act(() => FakeEventSource.last.fail({ closed: false }));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.last.closed).toBe(false);
    expect(api.listNotifications).toHaveBeenCalledTimes(1);
  });

  it("when the server refuses it, refetches (how a 401 is noticed) and reconnects with growing delay", async () => {
    vi.useFakeTimers();
    mount();
    await flush();

    const first = FakeEventSource.last;
    act(() => first.fail({ closed: true }));
    await flush();

    expect(first.closed).toBe(true);
    expect(api.listNotifications).toHaveBeenCalledTimes(2);
    expect(FakeEventSource.instances).toHaveLength(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(1999); });
    expect(FakeEventSource.instances).toHaveLength(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(FakeEventSource.instances).toHaveLength(2);

    act(() => FakeEventSource.last.fail({ closed: true }));
    await act(async () => { await vi.advanceTimersByTimeAsync(3999); });
    expect(FakeEventSource.instances).toHaveLength(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("resets the delay once a connection succeeds", async () => {
    vi.useFakeTimers();
    mount();
    await flush();

    act(() => FakeEventSource.last.fail({ closed: true }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    act(() => FakeEventSource.last.open());
    act(() => FakeEventSource.last.fail({ closed: true }));

    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it("closes the stream on unmount, and a pending reconnect never fires", async () => {
    vi.useFakeTimers();
    const { unmount } = mount();
    await flush();

    act(() => FakeEventSource.last.fail({ closed: true }));
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.last.closed).toBe(true);
  });
});

describe("provider: refetching when the tab is shown again", () => {
  const show = () => {
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  };

  it("refetches after a while away", async () => {
    vi.useFakeTimers();
    mount();
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(16_000); });

    show();
    await flush();

    expect(api.listNotifications).toHaveBeenCalledTimes(2);
  });

  it("but not on every flick between tabs", async () => {
    vi.useFakeTimers();
    mount();
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });

    show();
    await flush();

    expect(api.listNotifications).toHaveBeenCalledTimes(1);
  });
});

describe("provider: marking read", () => {
  it("responds at once, then trusts the server's count", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2)], { unread: 5 }));
    let resolvePatch;
    api.markNotificationRead.mockReturnValue(new Promise((resolve) => { resolvePatch = resolve; }));
    mount();
    await ready();

    let pending;
    act(() => { pending = ctx.markRead(3); });

    expect(text("statuses")).toBe("3:read,2:unread");
    expect(text("count")).toBe("4");

    await act(async () => {
      resolvePatch(read(n(3), 3));
      await pending;
    });

    expect(text("count")).toBe("3");
    expect(api.markNotificationRead).toHaveBeenCalledWith(3);
  });

  it("undoes it, and says so, if the server refuses", async () => {
    api.listNotifications.mockResolvedValue(page([n(3)], { unread: 5 }));
    api.markNotificationRead.mockResolvedValue({ ok: false, error: "HTTP 500" });
    mount();
    await ready();

    let result;
    await act(async () => { result = await ctx.markRead(3); });

    expect(result).toBe(false);
    expect(text("statuses")).toBe("3:unread");
    expect(text("count")).toBe("5");
    expect(await screen.findByText("Couldn't update the notification")).toBeInTheDocument();
  });

  it("does not call the server for one that is already read", async () => {
    api.listNotifications.mockResolvedValue(page([n(2, { status: "read" })], { unread: 0 }));
    mount();
    await ready();

    await act(async () => { await ctx.markRead(2); });

    expect(api.markNotificationRead).not.toHaveBeenCalled();
  });

  it("marks everything read", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2)], { unread: 40 }));
    api.markAllNotificationsRead.mockResolvedValue({ ok: true, data: { ok: true, data: { updated: 40, unread_count: 0 } } });
    mount();
    await ready();

    await act(async () => { await ctx.markAllRead(); });

    expect(text("statuses")).toBe("3:read,2:read");
    expect(text("count")).toBe("0");
  });

  it("asks the server what is true if marking all fails - there is no cheap local undo", async () => {
    api.listNotifications.mockResolvedValue(page([n(3)], { unread: 4 }));
    api.markAllNotificationsRead.mockResolvedValue({ ok: false, error: "HTTP 500" });
    mount();
    await ready();

    await act(async () => { await ctx.markAllRead(); });

    expect(await screen.findByText("Couldn't mark notifications as read")).toBeInTheDocument();
    expect(api.listNotifications).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(text("count")).toBe("4"));
  });
});

describe("provider: clearing", () => {
  it("empties everything at once, then takes the server's count", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2)], { unread: 40, next: 2 }));
    let resolveDelete;
    api.clearAllNotifications.mockReturnValue(new Promise((resolve) => { resolveDelete = resolve; }));
    mount();
    await ready();

    let pending;
    act(() => { pending = ctx.clearAll(); });

    expect(text("ids")).toBe("");
    expect(text("count")).toBe("0");
    expect(text("more")).toBe("false");

    await act(async () => {
      resolveDelete({ ok: true, data: { ok: true, data: { deleted: 40, unread_count: 1 } } });
      await pending;
    });

    expect(text("count")).toBe("1");
    expect(api.clearAllNotifications).toHaveBeenCalledTimes(1);
  });

  it("puts the list back, and says so, if the server could not delete", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2)], { unread: 2 }));
    api.clearAllNotifications.mockResolvedValue({ ok: false, error: "HTTP 500" });
    mount();
    await ready();

    await act(async () => { await ctx.clearAll(); });

    expect(await screen.findByText("Couldn't clear notifications")).toBeInTheDocument();
    await waitFor(() => expect(text("ids")).toBe("3,2"));
    expect(text("count")).toBe("2");
    expect(api.listNotifications).toHaveBeenCalledTimes(2);
  });

  it("a notification that arrives after clearing is kept", async () => {
    api.listNotifications.mockResolvedValue(page([n(3)], { unread: 1 }));
    api.clearAllNotifications.mockResolvedValue({ ok: true, data: { ok: true, data: { deleted: 1, unread_count: 0 } } });
    mount();
    await ready();
    await act(async () => { await ctx.clearAll(); });

    act(() => FakeEventSource.last.emit("notification", { notification: n(4), unread_count: 1 }));

    expect(text("ids")).toBe("4");
    expect(text("count")).toBe("1");
  });
});

describe("provider: paging", () => {
  it("loads the next page by cursor and appends it", async () => {
    api.listNotifications
      .mockResolvedValueOnce(page([n(5), n(4)], { unread: 2, next: 4 }))
      .mockResolvedValueOnce(page([n(4), n(3)], { unread: 2, next: null }));
    mount();
    await ready();

    await act(async () => { await ctx.loadMore(); });

    expect(api.listNotifications).toHaveBeenLastCalledWith({ limit: 20, before: 4 });
    expect(text("ids")).toBe("5,4,3");
    expect(text("more")).toBe("false");
  });

  it("does nothing when there is no older page", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { next: null }));
    mount();
    await ready();

    await act(async () => { await ctx.loadMore(); });

    expect(api.listNotifications).toHaveBeenCalledTimes(1);
  });

  it("does not start a second load while one is running", async () => {
    let resolveMore;
    api.listNotifications
      .mockResolvedValueOnce(page([n(5)], { next: 5 }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveMore = resolve; }));
    mount();
    await ready();

    act(() => { ctx.loadMore(); });
    act(() => { ctx.loadMore(); });

    expect(api.listNotifications).toHaveBeenCalledTimes(2);

    await act(async () => resolveMore(page([n(4)], { next: null })));
  });
});

describe("useNotifications", () => {
  it("refuses to be used outside its provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const swallow = (event) => event.preventDefault();
    window.addEventListener("error", swallow);

    expect(() => render(<Probe />)).toThrow(/NotificationsProvider/);

    window.removeEventListener("error", swallow);
    spy.mockRestore();
  });
});
