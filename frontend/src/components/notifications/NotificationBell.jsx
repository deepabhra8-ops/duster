import { useEffect, useRef, useState } from "react";
import { useNotifications } from "../../hooks/useNotifications.js";
import NotificationPanel from "./NotificationPanel.jsx";
import "../../styles/notifications.css";

const PANEL_ID = "notification-panel";

const BADGE_MAX = 99;

export default function NotificationBell() {
  const { unreadCount, refresh } = useNotifications();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(event) {
      if (event.target.closest?.(".toast-viewport")) return;

      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }

    function onKeyDown(event) {
      if (event.key !== "Escape") return;

      setOpen(false);
      buttonRef.current?.focus();
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function toggle() {
    if (!open) refresh();

    setOpen(!open);
  }

  const hasUnread = unreadCount > 0;

  return (
    <div className="notification-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="notification-btn"
        onClick={toggle}
        aria-label={hasUnread ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        title="Notifications"
      >
        <span className="notification-icon" aria-hidden="true" />

        {hasUnread ? (
          <span className="notification-badge" aria-hidden="true">
            {unreadCount > BADGE_MAX ? `${BADGE_MAX}+` : unreadCount}
          </span>
        ) : null}
      </button>

      <span className="sr-only" role="status" aria-live="polite">
        {hasUnread ? `${unreadCount} unread notifications` : "No unread notifications"}
      </span>

      {open ? <NotificationPanel id={PANEL_ID} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}
