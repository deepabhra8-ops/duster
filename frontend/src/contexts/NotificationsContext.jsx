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

const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 60_000;

const VISIBILITY_REFRESH_MIN_MS = 15_000;

const EVENT_SOURCE_CLOSED = 2;

export const initialNotificationsState = {
  items: [],
  unreadCount: 0,
  nextCursor: null,
  loaded: false,
  status: "loading",
  loadingMore: false,
  error: "",
};

const byNewest = (a, b) => b.id - a.id;

function insertSorted(items, notification) {
  return [...items, notification].sort(byNewest);
}

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

  const stateRef = useRef(state);
  stateRef.current = state;

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
    refresh();
  }, [refresh, showToast]);

  const clearAll = useCallback(async () => {
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

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
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
        refresh();
      };

      source.addEventListener("notification", (event) => {
        try {
          const { notification, unread_count: unreadCount } = JSON.parse(event.data);
          dispatch({ type: "received", notification, unreadCount });
        } catch {
        }
      });

      source.onerror = () => {
        if (source.readyState !== EVENT_SOURCE_CLOSED) return;

        source.close();

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
