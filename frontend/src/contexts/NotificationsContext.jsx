/**
 * NotificationsContext.jsx - app-wide notification state for the top bar's bell.
 *
 * A Context so the bell, and anything added later (a job page that wants to know a
 * notification arrived, a full notifications page), read one source of truth. Mounted by
 * AuthenticatedLayout, so it only exists while signed in: nothing is fetched or streamed on
 * the login screen, and signing out unmounts it - which is also what discards the state, since
 * none of it is persisted. Notification text is per-user data and stays out of storage.
 *
 * Where the numbers come from:
 *
 *  - `unreadCount` is the server's TOTAL, not the number of unread rows held here. The list is
 *    paged, so counting what is loaded would under-report the badge as soon as a user had more
 *    than a page. Marking read adjusts it optimistically and is then corrected from the
 *    response; a live event carries the server's count, so a badge that drifted (say, from
 *    marking things read in another tab) corrects itself on the next arrival.
 *
 *  - New notifications arrive over a Server-Sent Events stream. It only says "here is one that
 *    is new since you connected" - history comes from the list request, which is re-issued every
 *    time the stream (re)opens. That refetch is what closes the window between the first load
 *    and the stream starting, and any gap while the connection was down, so no client-side
 *    bookkeeping of "what did I miss" is needed.
 *
 *  - The stream is deliberately not a heartbeat for the session. The server authenticates it
 *    without extending the session, so an idle tab still times out; when the session does end,
 *    the stream is refused with a 401 and the request below is what carries that to the app's
 *    sign-out handling.
 */
import { createContext, useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import {
  clearAllNotifications,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notificationStreamUrl,
} from "../api/api.js";
import { useToast } from "../hooks/useToast.js";

export const NotificationsContext = createContext(null);

const PAGE_SIZE = 20;

/** Backoff for reopening a stream the server refused: 2s, 4s, ... capped. The browser retries a dropped connection itself. */
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 60_000;

/** Coming back to the tab refetches, but not more often than this. */
const VISIBILITY_REFRESH_MIN_MS = 15_000;

/** EventSource.CLOSED, spelled out so this module can load where EventSource does not exist. */
const EVENT_SOURCE_CLOSED = 2;

export const initialNotificationsState = {
  /** Newest first, by id. Only what has been loaded or pushed - not necessarily everything. */
  items: [],
  /** The user's total unread, as last told by the server (see file header). */
  unreadCount: 0,
  /** Pass as `before` to load the next page; null when there is no older one. */
  nextCursor: null,
  /** Whether a first page has ever arrived. */
  loaded: false,
  status: "loading", // "loading" until the first response, then "ready"
  loadingMore: false,
  error: "",
};

const byNewest = (a, b) => b.id - a.id;

function insertSorted(items, notification) {
  return [...items, notification].sort(byNewest);
}

/**
 * Fold a freshly fetched first page into what is already held.
 *
 * Replacing the list would throw away every page the user had scrolled through each time the
 * popover was opened, and reset their scroll. So when the new page overlaps or touches what is
 * held, the two are joined and the newer copy of any row wins (it may have been marked read
 * elsewhere), and the cursor already held is kept because it points further back.
 *
 * When they do not touch, there is a hole in between - more than a page arrived while this
 * client was not listening. Joining would hide it and leave a cursor that skips it, so the held
 * list is dropped in favour of the fresh page.
 */
function mergeFirstPage(state, incoming, incomingCursor) {
  const oldestIncoming = incoming.length ? Math.min(...incoming.map((n) => n.id)) : Infinity;
  const newestHeld = state.items.length ? state.items[0].id : -Infinity;
  const contiguous = state.loaded && oldestIncoming <= newestHeld;

  if (!contiguous) {
    return { items: incoming, nextCursor: incomingCursor };
  }

  const merged = new Map(state.items.map((n) => [n.id, n]));
  incoming.forEach((n) => merged.set(n.id, n));

  return { items: [...merged.values()].sort(byNewest), nextCursor: state.nextCursor };
}

export function notificationsReducer(state, action) {
  switch (action.type) {
    case "refreshed": {
      const merged = mergeFirstPage(state, action.items, action.nextCursor);

      return {
        ...state,
        items: merged.items,
        nextCursor: merged.nextCursor,
        unreadCount: action.unreadCount,
        loaded: true,
        status: "ready",
        error: "",
      };
    }

    case "refreshFailed":
      return { ...state, status: "ready", error: action.error };

    case "loadMoreStarted":
      return { ...state, loadingMore: true, error: "" };

    case "loadedMore": {
      const merged = new Map(state.items.map((n) => [n.id, n]));
      action.items.forEach((n) => merged.set(n.id, n));

      return {
        ...state,
        items: [...merged.values()].sort(byNewest),
        nextCursor: action.nextCursor,
        loadingMore: false,
      };
    }

    case "loadMoreFailed":
      return { ...state, loadingMore: false, error: action.error };

    // A notification pushed by the stream. Already held (the list request and the stream can
    // both deliver the same one) means nothing to add - but the count it carries is still fresh.
    case "received": {
      const held = state.items.some((n) => n.id === action.notification.id);

      return {
        ...state,
        items: held ? state.items : insertSorted(state.items, action.notification),
        unreadCount: action.unreadCount ?? state.unreadCount + (held ? 0 : 1),
      };
    }

    case "markedReadLocal": {
      const target = state.items.find((n) => n.id === action.id);

      if (!target || target.status === "read") return state;

      return {
        ...state,
        items: state.items.map((n) => (n.id === action.id ? { ...n, status: "read" } : n)),
        unreadCount: Math.max(0, state.unreadCount - 1),
      };
    }

    // Undo of markedReadLocal after the server refused it.
    case "markReadReverted": {
      const target = state.items.find((n) => n.id === action.id);

      if (!target || target.status !== "read") return state;

      return {
        ...state,
        items: state.items.map((n) => (n.id === action.id ? { ...n, status: "unread" } : n)),
        unreadCount: state.unreadCount + 1,
      };
    }

    case "allMarkedReadLocal":
      return {
        ...state,
        items: state.items.map((n) => (n.status === "read" ? n : { ...n, status: "read" })),
        unreadCount: 0,
      };

    // Everything deleted, including pages never loaded - which is why the cursor goes too.
    case "allClearedLocal":
      return { ...state, items: [], nextCursor: null, unreadCount: 0, error: "" };

    case "countSynced":
      return { ...state, unreadCount: action.unreadCount };

    default:
      return state;
  }
}

export function NotificationsProvider({ children }) {
  const [state, dispatch] = useReducer(notificationsReducer, initialNotificationsState);
  const { showToast } = useToast();

  // Callbacks read the latest state through this instead of closing over it, so they keep a
  // stable identity and the effects below do not tear the stream down on every render.
  const stateRef = useRef(state);
  stateRef.current = state;

  // Only the newest refresh may write. Two can be in flight at once (the initial load and the
  // stream opening); without this, the slower one finishing last would overwrite the fresher.
  const refreshTicket = useRef(0);

  const refresh = useCallback(async () => {
    const ticket = ++refreshTicket.current;
    const res = await listNotifications({ limit: PAGE_SIZE });

    if (ticket !== refreshTicket.current) return;

    const page = res.ok ? res.data?.data : null;

    if (page) {
      dispatch({
        type: "refreshed",
        items: page.items,
        unreadCount: page.unread_count,
        nextCursor: page.next_cursor,
      });
    } else {
      dispatch({ type: "refreshFailed", error: res.error || "Could not load notifications" });
    }
  }, []);

  const loadMore = useCallback(async () => {
    const { nextCursor, loadingMore } = stateRef.current;

    if (nextCursor == null || loadingMore) return;

    dispatch({ type: "loadMoreStarted" });
    const res = await listNotifications({ limit: PAGE_SIZE, before: nextCursor });
    const page = res.ok ? res.data?.data : null;

    if (page) {
      dispatch({ type: "loadedMore", items: page.items, nextCursor: page.next_cursor });
    } else {
      dispatch({ type: "loadMoreFailed", error: res.error || "Could not load older notifications" });
    }
  }, []);

  const markRead = useCallback(
    async (id) => {
      const target = stateRef.current.items.find((n) => n.id === id);

      if (!target || target.status === "read") return true;

      // Optimistic: the badge and the row respond at once instead of after a round trip.
      dispatch({ type: "markedReadLocal", id });
      const res = await markNotificationRead(id);

      if (res.ok) {
        const count = res.data?.data?.unread_count;
        if (typeof count === "number") dispatch({ type: "countSynced", unreadCount: count });
        return true;
      }

      dispatch({ type: "markReadReverted", id });
      showToast({ type: "error", title: "Couldn't update the notification", message: res.error });
      return false;
    },
    [showToast]
  );

  const markAllRead = useCallback(async () => {
    dispatch({ type: "allMarkedReadLocal" });
    const res = await markAllNotificationsRead();

    if (res.ok) {
      const count = res.data?.data?.unread_count;
      if (typeof count === "number") dispatch({ type: "countSynced", unreadCount: count });
      return;
    }

    showToast({ type: "error", title: "Couldn't mark notifications as read", message: res.error });
    // Unlike a single row there is no cheap local undo, so ask the server what is true.
    refresh();
  }, [refresh, showToast]);

  const clearAll = useCallback(async () => {
    // Optimistic, like everything else here. Not undoable server-side, but if the request fails
    // nothing was deleted, so the list is put back by asking the server what is really there.
    dispatch({ type: "allClearedLocal" });
    const res = await clearAllNotifications();

    if (res.ok) {
      const count = res.data?.data?.unread_count;
      if (typeof count === "number") dispatch({ type: "countSynced", unreadCount: count });
      return;
    }

    showToast({ type: "error", title: "Couldn't clear notifications", message: res.error });
    refresh();
  }, [refresh, showToast]);

  // Initial load, so the badge is right before anyone opens the popover - and stays right even
  // if the live stream never manages to connect.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Live updates.
  useEffect(() => {
    // Very old browsers (and jsdom). Everything still works; it just is not live.
    if (typeof EventSource === "undefined") return undefined;

    let source = null;
    let retryTimer = null;
    let attempt = 0;
    let stopped = false;

    function connect() {
      if (stopped) return;

      source = new EventSource(notificationStreamUrl(), { withCredentials: true });

      source.onopen = () => {
        attempt = 0;
        // See the file header: this is what makes "start from now" on the server lossless.
        refresh();
      };

      source.addEventListener("notification", (event) => {
        try {
          const { notification, unread_count: unreadCount } = JSON.parse(event.data);
          dispatch({ type: "received", notification, unreadCount });
        } catch {
          // A frame this client cannot read is not worth breaking the stream over.
        }
      });

      source.onerror = () => {
        // Still CONNECTING: the browser is retrying by itself. CLOSED: the server refused the
        // request (a 401 once the session has ended, or a 5xx) and the browser will not try again.
        if (source.readyState !== EVENT_SOURCE_CLOSED) return;

        source.close();

        // A 401 here is how a signed-out session is noticed: this request goes through axios,
        // whose interceptor hands it to the app-wide sign-out handling.
        refresh();

        const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** attempt);
        attempt += 1;
        retryTimer = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(retryTimer);
      source?.close();
    };
  }, [refresh]);

  // Another tab may have marked things read, or notifications may have arrived while this one
  // was in the background and its stream throttled. Returning to the tab is the natural moment.
  useEffect(() => {
    let last = Date.now();

    function onVisibilityChange() {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - last < VISIBILITY_REFRESH_MIN_MS) return;

      last = Date.now();
      refresh();
    }

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [refresh]);

  const value = useMemo(
    () => ({
      items: state.items,
      unreadCount: state.unreadCount,
      hasMore: state.nextCursor != null,
      status: state.status,
      loadingMore: state.loadingMore,
      error: state.error,
      refresh,
      loadMore,
      markRead,
      markAllRead,
      clearAll,
    }),
    [state, refresh, loadMore, markRead, markAllRead, clearAll]
  );

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
}

export default NotificationsProvider;
