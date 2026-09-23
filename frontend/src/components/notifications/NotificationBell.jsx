/**
 * NotificationBell.jsx - the top bar's bell: unread badge plus the popover it opens.
 *
 * Accessibility:
 *  - The button's name carries the count ("Notifications, 3 unread"), so it is known before it is
 *    opened, and it is a disclosure control (aria-expanded / aria-controls) for a non-modal dialog.
 *  - A changing aria-label is not announced by screen readers on its own, so a polite live region
 *    says "N unread notifications" when the count changes - that is what makes a notification
 *    arriving in real time perceivable without looking at the badge.
 *  - The visible badge is aria-hidden: the label and live region already say it, and reading "3"
 *    on top of that would be noise.
 *  - Escape closes and returns focus to the bell; a press outside closes too (as AccountMenu does).
 *  - The panel sits right after the button in the DOM, so Tab moves into it naturally.
 */
import { useEffect, useRef, useState } from "react";
import { useNotifications } from "../../hooks/useNotifications.js";
import NotificationPanel from "./NotificationPanel.jsx";
import "../../styles/notifications.css";

const PANEL_ID = "notification-panel";

/** The pill is small; past this it reads "99+" rather than growing. */
const BADGE_MAX = 99;

export default function NotificationBell() {
  const { unreadCount, refresh } = useNotifications();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(event) {
      // A toast is not "outside" in any sense the user would recognise: it is the app answering
      // something they just did in this panel, and it is pinned under the bell - i.e. it can sit
      // right over the panel's header. Closing the panel because they pressed the toast's dismiss
      // button would throw away where they were working.
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
    // Opening is the moment to be sure of what is shown: another tab may have changed things,
    // and the stream may have been down.
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
