import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

import * as api from "../../api/api.js";
import { NotificationsProvider } from "../../contexts/NotificationsContext.jsx";
import { ToastProvider } from "../../contexts/ToastContext.jsx";
import { FakeEventSource } from "../../test/fakeEventSource.js";
import NotificationBell from "./NotificationBell.jsx";

vi.mock("../../api/api.js", () => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  clearAllNotifications: vi.fn(),
  notificationStreamUrl: () => "http://test/api/notifications/stream",
}));

const minutesAgo = (m) => new Date(Date.now() - m * 60_000).toISOString();

const n = (id, over = {}) => ({
  id,
  type: "job_done",
  title: `Job ${id} completed`,
  content: `Body ${id}`,
  status: "unread",
  link: `/validator/${id}`,
  created_at: minutesAgo(id),
  ...over,
});

const page = (items, { unread = items.filter((i) => i.status === "unread").length, next = null } = {}) => ({
  ok: true,
  data: { ok: true, data: { items, unread_count: unread, next_cursor: next } },
});

const readReply = (notification, unread) => ({
  ok: true,
  data: { ok: true, data: { notification: { ...notification, status: "read" }, unread_count: unread } },
});

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/home"]}>
      <ToastProvider>
        <NotificationsProvider>
          <NotificationBell />
          <Where />
        </NotificationsProvider>
      </ToastProvider>
    </MemoryRouter>
  );
}

const bell = () => screen.getByRole("button", { name: /^Notifications/ });
const badge = () => document.querySelector(".notification-badge");
const openPanel = async () => {
  fireEvent.click(bell());
  return screen.findByRole("dialog", { name: "Notifications" });
};

const settled = () => act(async () => { await Promise.resolve(); });

beforeEach(() => {
  vi.resetAllMocks();
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
  api.listNotifications.mockResolvedValue(page([]));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("badge", () => {
  it("is absent when nothing is unread, and the button is plainly named", async () => {
    mount();
    await settled();

    expect(badge()).toBeNull();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("shows the unread count, and puts it in the button's accessible name", async () => {
    api.listNotifications.mockResolvedValue(page([n(1), n(2)], { unread: 7 }));
    mount();

    await waitFor(() => expect(badge()).toHaveTextContent("7"));
    expect(screen.getByRole("button", { name: "Notifications, 7 unread" })).toBeInTheDocument();
  });

  it("counts the server's total, not just the rows it has loaded", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 58 }));
    mount();

    await waitFor(() => expect(badge()).toHaveTextContent("58"));
  });

  it("caps at 99+ instead of growing", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 250 }));
    mount();

    await waitFor(() => expect(badge()).toHaveTextContent("99+"));
    expect(bell()).toHaveAccessibleName("Notifications, 250 unread");
  });

  it("is hidden from assistive tech, since the label and live region already say it", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 3 }));
    mount();

    await waitFor(() => expect(badge()).toHaveAttribute("aria-hidden", "true"));
  });

  it("increments the moment a notification is pushed, with the panel closed", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 1 }));
    mount();
    await waitFor(() => expect(badge()).toHaveTextContent("1"));

    act(() => FakeEventSource.last.emit("notification", { notification: n(2), unread_count: 2 }));

    expect(badge()).toHaveTextContent("2");
    expect(bell()).toHaveAccessibleName("Notifications, 2 unread");
  });

  it("appears when the first notification arrives on an empty bell", async () => {
    mount();
    await settled();
    expect(badge()).toBeNull();

    act(() => FakeEventSource.last.emit("notification", { notification: n(1), unread_count: 1 }));

    expect(badge()).toHaveTextContent("1");
  });

  it("announces the count through a polite live region, since a changed label is not announced", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 1 }));
    mount();
    await waitFor(() => expect(badge()).toHaveTextContent("1"));

    const live = screen.getByRole("status");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent("1 unread notifications");

    act(() => FakeEventSource.last.emit("notification", { notification: n(2), unread_count: 2 }));

    expect(live).toHaveTextContent("2 unread notifications");
  });

  it("drops away when everything has been read", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 1 }));
    api.markNotificationRead.mockResolvedValue(readReply(n(1), 0));
    mount();
    await waitFor(() => expect(badge()).toHaveTextContent("1"));

    const dialog = await openPanel();
    fireEvent.click(within(dialog).getByRole("button", { name: /Job 1 completed/ }));

    await waitFor(() => expect(badge()).toBeNull());
  });
});

describe("popover", () => {
  it("opens on click, as a labelled dialog the button controls", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)]));
    mount();
    await settled();

    expect(bell()).toHaveAttribute("aria-expanded", "false");
    expect(bell()).toHaveAttribute("aria-haspopup", "dialog");

    const dialog = await openPanel();

    expect(bell()).toHaveAttribute("aria-expanded", "true");
    expect(bell()).toHaveAttribute("aria-controls", dialog.id);
    expect(dialog).toHaveAccessibleName("Notifications");
  });

  it("closes when the bell is clicked again", async () => {
    mount();
    await settled();
    await openPanel();

    fireEvent.click(bell());

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(bell()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on Escape and hands focus back to the bell", async () => {
    mount();
    await settled();
    const dialog = await openPanel();
    within(dialog).getByRole("button", { name: "Mark all as read" }).focus();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(bell()).toHaveFocus();
  });

  it("closes on a press outside, but not inside", async () => {
    mount();
    await settled();
    const dialog = await openPanel();

    fireEvent.mouseDown(dialog);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("stays open when a toast is pressed - one can sit over the panel, and dismissing it must not close it", async () => {
    mount();
    await settled();
    await openPanel();
    const viewport = document.createElement("div");
    viewport.className = "toast-viewport";
    const dismiss = document.createElement("button");
    viewport.appendChild(dismiss);
    document.body.appendChild(viewport);

    fireEvent.mouseDown(dismiss);

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    viewport.remove();
  });

  it("refetches every time it is opened, in case another tab changed things", async () => {
    mount();
    await settled();
    const before = api.listNotifications.mock.calls.length;

    await openPanel();

    expect(api.listNotifications.mock.calls.length).toBe(before + 1);
  });

  it("shows each notification's title, message, time and read state", async () => {
    api.listNotifications.mockResolvedValue(
      page([
        n(9, {
          title: "Validator job failed",
          content: "Q3 claims did not finish.",
          created_at: minutesAgo(5),
        }),
        n(5, { status: "read" }),
      ])
    );
    mount();
    await settled();

    const dialog = await openPanel();
    const items = within(dialog).getAllByRole("listitem");

    expect(items).toHaveLength(2);

    const unread = items[0];
    expect(within(unread).getByText("Validator job failed")).toBeInTheDocument();
    expect(within(unread).getByText("Q3 claims did not finish.")).toBeInTheDocument();
    expect(within(unread).getByText("5 minutes ago")).toBeInTheDocument();
    expect(unread.querySelector("time")).toHaveAttribute("dateTime");
    expect(unread.querySelector(".notification-item")).toHaveClass("is-unread");
  });

  it("tells read from unread in text as well as styling, for screen readers", async () => {
    api.listNotifications.mockResolvedValue(page([n(2), n(1, { status: "read" })]));
    mount();
    await settled();

    const dialog = await openPanel();
    const [unread, read] = within(dialog).getAllByRole("listitem");

    expect(unread).toHaveTextContent("Unread:");
    expect(read).toHaveTextContent("Read:");
    expect(read.querySelector(".notification-item")).toHaveClass("is-read");
  });

  it("lists newest first", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2), n(1)]));
    mount();
    await settled();

    const dialog = await openPanel();
    const titles = within(dialog).getAllByRole("listitem").map((li) => li.textContent);

    expect(titles[0]).toContain("Job 3");
    expect(titles[2]).toContain("Job 1");
  });

  it("gains a notification pushed while it is open", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)]));
    mount();
    await settled();
    const dialog = await openPanel();

    act(() => FakeEventSource.last.emit("notification", { notification: n(2, { title: "Brand new" }), unread_count: 2 }));

    expect(within(dialog).getAllByRole("listitem")[0]).toHaveTextContent("Brand new");
  });
});

describe("selecting a notification", () => {
  it("marks it read, closes the panel, and goes to its link", async () => {
    api.listNotifications.mockResolvedValue(page([n(4, { link: "/validator/abc" })], { unread: 1 }));
    api.markNotificationRead.mockResolvedValue(readReply(n(4), 0));
    mount();
    await settled();
    const dialog = await openPanel();

    fireEvent.click(within(dialog).getByRole("button", { name: /Job 4 completed/ }));

    expect(api.markNotificationRead).toHaveBeenCalledWith(4);
    expect(screen.getByTestId("where")).toHaveTextContent("/validator/abc");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each(["https://evil.example/phish", "//evil.example", "/\\evil.example", "javascript:alert(1)"])(
    "will not follow %s - it still marks it read, and stays put",
    async (link) => {
      api.listNotifications.mockResolvedValue(page([n(4, { link })], { unread: 1 }));
      api.markNotificationRead.mockResolvedValue(readReply(n(4), 0));
      mount();
      await settled();
      const dialog = await openPanel();

      fireEvent.click(within(dialog).getByRole("button", { name: /Job 4 completed/ }));

      expect(api.markNotificationRead).toHaveBeenCalledWith(4);
      expect(screen.getByTestId("where")).toHaveTextContent("/home");
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    }
  );

  it("with no link, marks it read and stays open for the next one", async () => {
    api.listNotifications.mockResolvedValue(page([n(4, { link: null }), n(3)], { unread: 2 }));
    api.markNotificationRead.mockResolvedValue(readReply(n(4), 1));
    mount();
    await settled();
    const dialog = await openPanel();

    fireEvent.click(within(dialog).getByRole("button", { name: /Job 4 completed/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/home");
    await waitFor(() => expect(badge()).toHaveTextContent("1"));
  });

  it("does not ask the server again for one that is already read, but still follows the link", async () => {
    api.listNotifications.mockResolvedValue(page([n(4, { status: "read", link: "/rules" })], { unread: 0 }));
    mount();
    await settled();
    const dialog = await openPanel();

    fireEvent.click(within(dialog).getByRole("button", { name: /Job 4 completed/ }));

    expect(api.markNotificationRead).not.toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/rules");
  });
});

describe("mark all as read", () => {
  it("clears the badge and every row", async () => {
    api.listNotifications.mockResolvedValue(page([n(2), n(1)], { unread: 9 }));
    api.markAllNotificationsRead.mockResolvedValue({ ok: true, data: { ok: true, data: { updated: 9, unread_count: 0 } } });
    mount();
    await waitFor(() => expect(badge()).toHaveTextContent("9"));
    const dialog = await openPanel();

    fireEvent.click(within(dialog).getByRole("button", { name: "Mark all as read" }));

    await waitFor(() => expect(badge()).toBeNull());
    within(dialog).getAllByRole("listitem").forEach((li) => {
      expect(li.querySelector(".notification-item")).toHaveClass("is-read");
    });
  });

  it("is disabled when there is nothing to mark", async () => {
    api.listNotifications.mockResolvedValue(page([n(1, { status: "read" })], { unread: 0 }));
    mount();
    await settled();
    const dialog = await openPanel();

    expect(within(dialog).getByRole("button", { name: "Mark all as read" })).toBeDisabled();
  });
});

describe("clear all", () => {
  const cleared = (deleted, unread = 0) => ({ ok: true, data: { ok: true, data: { deleted, unread_count: unread } } });

  it("sits beside 'Mark all as read' in the header", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)]));
    mount();
    await settled();

    const dialog = await openPanel();
    const header = dialog.querySelector(".notification-panel-header");

    expect(within(header).getByRole("button", { name: "Mark all as read" })).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Clear all" })).toBeInTheDocument();
  });

  it("deletes everything on one click: rows, badge, and the server call", async () => {
    api.listNotifications.mockResolvedValue(page([n(3), n(2, { status: "read" }), n(1)], { unread: 12 }));
    api.clearAllNotifications.mockResolvedValue(cleared(15));
    mount();
    await waitFor(() => expect(badge()).toHaveTextContent("12"));
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    fireEvent.click(within(dialog).getByRole("button", { name: "Clear all" }));

    await waitFor(() => expect(within(dialog).queryAllByRole("listitem")).toHaveLength(0));
    expect(api.clearAllNotifications).toHaveBeenCalledTimes(1);
    expect(badge()).toBeNull();
    expect(within(dialog).getByText(/all caught up/i)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Load older/ })).toBeNull();
  });

  it("removes read notifications too, not just unread ones", async () => {
    api.listNotifications.mockResolvedValue(page([n(2, { status: "read" }), n(1, { status: "read" })], { unread: 0 }));
    api.clearAllNotifications.mockResolvedValue(cleared(2));
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    fireEvent.click(within(dialog).getByRole("button", { name: "Clear all" }));

    await waitFor(() => expect(within(dialog).queryAllByRole("listitem")).toHaveLength(0));
    expect(api.clearAllNotifications).toHaveBeenCalledTimes(1);
  });

  it("is disabled, along with 'Mark all as read', when there is nothing to clear", async () => {
    mount();
    await settled();
    const dialog = await openPanel();

    expect(within(dialog).getByRole("button", { name: "Clear all" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Mark all as read" })).toBeDisabled();
  });

  it("brings the list back if the server refuses, and tells the user", async () => {
    api.listNotifications.mockResolvedValue(page([n(2), n(1)], { unread: 2 }));
    api.clearAllNotifications.mockResolvedValue({ ok: false, error: "HTTP 500" });
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    fireEvent.click(within(dialog).getByRole("button", { name: "Clear all" }));

    expect(await screen.findByText("Couldn't clear notifications")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getAllByRole("listitem")).toHaveLength(2));
    expect(badge()).toHaveTextContent("2");
  });

  it("keeps working live afterwards: a new notification shows up in the emptied panel", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { unread: 1 }));
    api.clearAllNotifications.mockResolvedValue(cleared(1));
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");
    fireEvent.click(within(dialog).getByRole("button", { name: "Clear all" }));
    await waitFor(() => expect(within(dialog).queryAllByRole("listitem")).toHaveLength(0));

    act(() => FakeEventSource.last.emit("notification", { notification: n(2, { title: "After clear" }), unread_count: 1 }));

    expect(within(dialog).getByText("After clear")).toBeInTheDocument();
    expect(badge()).toHaveTextContent("1");
  });
});

describe("infinite scroll", () => {
  const pane = (dialog) => dialog.querySelector(".notification-panel-body");

  const scrollTo = (el, { top, height = 1000, client = 300 }) => {
    Object.defineProperty(el, "scrollHeight", { value: height, configurable: true });
    Object.defineProperty(el, "clientHeight", { value: client, configurable: true });
    Object.defineProperty(el, "scrollTop", { value: top, configurable: true });
    fireEvent.scroll(el);
  };

  const serve = (first, more) =>
    api.listNotifications.mockImplementation(({ before } = {}) => (before ? more : Promise.resolve(first)));

  const pagedRequests = () => api.listNotifications.mock.calls.filter(([options]) => options?.before);

  it("loads the next page when the user nears the bottom, and appends it", async () => {
    serve(
      page([n(5), n(4)], { unread: 2, next: 4 }),
      Promise.resolve(page([n(3), n(2)], { unread: 2, next: null }))
    );
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    scrollTo(pane(dialog), { top: 650 });

    await waitFor(() => expect(within(dialog).getAllByRole("listitem")).toHaveLength(4));
    expect(api.listNotifications).toHaveBeenCalledWith({ limit: 20, before: 4 });
  });

  it("does not load while the user is still far from the bottom", async () => {
    serve(page([n(5), n(4)], { unread: 2, next: 4 }), Promise.resolve(page([])));
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    scrollTo(pane(dialog), { top: 0 });

    expect(pagedRequests()).toHaveLength(0);
  });

  it("does not load twice for a burst of scroll events", async () => {
    let resolveMore;
    serve(
      page([n(5), n(4)], { unread: 2, next: 4 }),
      new Promise((resolve) => { resolveMore = resolve; })
    );
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    scrollTo(pane(dialog), { top: 650 });
    scrollTo(pane(dialog), { top: 660 });
    scrollTo(pane(dialog), { top: 670 });

    expect(pagedRequests()).toHaveLength(1);

    await act(async () => resolveMore(page([n(3)], { unread: 2, next: null })));
  });

  it("offers a button too, for anyone who never scrolls the pane, and it is the loading indicator", async () => {
    let resolveMore;
    serve(
      page([n(5)], { unread: 1, next: 5 }),
      new Promise((resolve) => { resolveMore = resolve; })
    );
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    fireEvent.click(within(dialog).getByRole("button", { name: "Load older notifications" }));

    const busy = await within(dialog).findByRole("button", { name: "Loading…" });
    expect(busy).toBeDisabled();

    await act(async () => resolveMore(page([n(4)], { unread: 1, next: null })));

    await waitFor(() => expect(within(dialog).getAllByRole("listitem")).toHaveLength(2));
    expect(within(dialog).queryByRole("button", { name: /Load older|Loading/ })).toBeNull();
  });

  it("offers no 'load older' when the whole history is already showing", async () => {
    api.listNotifications.mockResolvedValue(page([n(1)], { next: null }));
    mount();
    await settled();
    const dialog = await openPanel();
    await within(dialog).findAllByRole("listitem");

    expect(within(dialog).queryByRole("button", { name: /Load older/ })).toBeNull();
  });
});

describe("empty, loading and error states", () => {
  it("says so when there is nothing, rather than showing an empty box", async () => {
    mount();
    await settled();

    const dialog = await openPanel();

    expect(await within(dialog).findByText(/all caught up/i)).toBeInTheDocument();
    expect(within(dialog).queryByRole("list")).toBeNull();
  });

  it("shows a loading state until the first response lands", async () => {
    let resolveFirst;
    api.listNotifications.mockReturnValue(new Promise((resolve) => { resolveFirst = resolve; }));
    mount();

    const dialog = await openPanel();
    expect(within(dialog).getByText("Loading…")).toBeInTheDocument();

    await act(async () => resolveFirst(page([n(1)])));

    expect(within(dialog).queryByText("Loading…")).toBeNull();
  });

  it("shows the failure with a way to retry, and recovers", async () => {
    api.listNotifications.mockResolvedValue({ ok: false, error: "The server took too long to respond." });
    mount();
    await settled();
    const dialog = await openPanel();

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The server took too long to respond.");

    api.listNotifications.mockResolvedValue(page([n(1)]));
    fireEvent.click(within(dialog).getByRole("button", { name: "Try again" }));

    expect(await within(dialog).findByText("Job 1 completed")).toBeInTheDocument();
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  it("keeps the list on screen when only a refresh fails", async () => {
    api.listNotifications.mockResolvedValueOnce(page([n(1)]));
    mount();
    await settled();
    api.listNotifications.mockResolvedValue({ ok: false, error: "offline" });

    const dialog = await openPanel();

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("offline");
    expect(within(dialog).getByText("Job 1 completed")).toBeInTheDocument();
  });
});
