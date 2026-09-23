/**
 * useNotifications.js - access the app-wide notification state (NotificationsContext.jsx):
 * `{ items, unreadCount, hasMore, status, loadingMore, error, refresh, loadMore, markRead, markAllRead, clearAll }`.
 */
import { useContext } from "react";
import { NotificationsContext } from "../contexts/NotificationsContext.jsx";

export function useNotifications() {
  const ctx = useContext(NotificationsContext);
  if (!ctx) {
    throw new Error("useNotifications() must be used within a <NotificationsProvider>");
  }
  return ctx;
}

export default useNotifications;
