import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useNotifications } from "../../hooks/useNotifications.js";
import { isInternalPath } from "../../utils/notifications.js";
import NotificationItem from "./NotificationItem.jsx";

const SCROLL_THRESHOLD_PX = 80;

const CLOCK_TICK_MS = 30_000;

export default function NotificationPanel({ id, onClose }) {
  const {
    items,
    unreadCount,
    hasMore,
    status,
    loadingMore,
    error,
    refresh,
    loadMore,
    markRead,
    markAllRead,
    clearAll,
  } = useNotifications();
  const navigate = useNavigate();

  const [, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  function handleSelect(notification) {
    markRead(notification.id);

    if (isInternalPath(notification.link)) {
      onClose();
      navigate(notification.link);
    }
  }

  function handleScroll(event) {
    const pane = event.currentTarget;
    const remaining = pane.scrollHeight - pane.scrollTop - pane.clientHeight;

    if (hasMore && !loadingMore && remaining < SCROLL_THRESHOLD_PX) loadMore();
  }

  let body;

  if (status === "loading") {
    body = (
      <p className="notification-state" role="status">
        Loading…
      </p>
    );
  } else if (items.length === 0 && error) {
    body = (
      <div className="notification-state" role="alert">
        <p>{error}</p>
        <button type="button" className="notification-link-btn" onClick={refresh}>
          Try again
        </button>
      </div>
    );
  } else if (items.length === 0) {
    body = (
      <p className="notification-state">You&rsquo;re all caught up.</p>
    );
  } else {
    body = (
      <>
        {error ? (
          <div className="notification-inline-error" role="alert">
            <span>{error}</span>
            <button type="button" className="notification-link-btn" onClick={refresh}>
              Try again
            </button>
          </div>
        ) : null}

        <ul className="notification-list" role="list">
          {items.map((notification) => (
            <NotificationItem key={notification.id} notification={notification} onSelect={handleSelect} />
          ))}
        </ul>

        {hasMore ? (
          <button
            type="button"
            className="notification-load-more"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? "Loading…" : "Load older notifications"}
          </button>
        ) : null}
      </>
    );
  }

  return (
    <div id={id} className="notification-panel" role="dialog" aria-labelledby={`${id}-title`}>
      <div className="notification-panel-header">
        <h2 id={`${id}-title`} className="notification-panel-title">
          Notifications
        </h2>

        <div className="notification-panel-actions">
          <button
            type="button"
            className="notification-link-btn"
            onClick={markAllRead}
            disabled={unreadCount === 0}
          >
            Mark all as read
          </button>

          <button
            type="button"
            className="notification-link-btn is-danger"
            onClick={clearAll}
            disabled={items.length === 0}
          >
            Clear all
          </button>
        </div>
      </div>

      <div className="notification-panel-body" onScroll={handleScroll}>
        {body}
      </div>
    </div>
  );
}
