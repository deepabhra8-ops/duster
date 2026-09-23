/**
 * NotificationPanel.jsx - the popover under the bell: a header, and a scrollable, paged list.
 *
 * Paging is by scroll: nearing the bottom asks for the next page. There is also a visible
 * "Load older" button, which is not redundant - it is what a keyboard or screen-reader user
 * reaches (they may never scroll the pane), and it doubles as the loading indicator.
 *
 * Owns no notification state; everything comes from NotificationsContext, so the bell's badge
 * and this list cannot disagree.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useNotifications } from "../../hooks/useNotifications.js";
import { isInternalPath } from "../../utils/notifications.js";
import NotificationItem from "./NotificationItem.jsx";

/** Ask for the next page when this close to the bottom of the list. */
const SCROLL_THRESHOLD_PX = 80;

/** Relative times ("2 minutes ago") are recomputed this often while the panel is open. */
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

  // Only here to force a re-render, so stamps do not go stale under a panel left open.
  const [, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  function handleSelect(notification) {
    markRead(notification.id);

    // Without a usable link there is nowhere to go, so stay open: the person is most likely
    // working down the list. isInternalPath is a second check on top of the server's - this
    // is the code that actually navigates.
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

        {/* role="list" is not redundant: Safari/VoiceOver drop list semantics from a <ul> styled
            with list-style: none, which is how this one is. */}
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

          {/* Deletes, for good, every notification the user has - read or not, loaded or not -
              so unlike its neighbour it cannot be undone. Kept apart by its red hover. */}
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
