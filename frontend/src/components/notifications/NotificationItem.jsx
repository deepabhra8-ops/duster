/**
 * NotificationItem.jsx - one row in the bell's notification list.
 *
 * A button, not a link, because selecting it does two things - marks it read, and follows its
 * link if it has one that stays inside the app - and the panel decides which (see
 * NotificationPanel.handleSelect).
 *
 * Read and unread differ in weight, tint and a leading marker, and ALSO in text for assistive
 * technology: colour and weight alone would leave a screen-reader user unable to tell them apart.
 */
import { classNames, fmtDate, fmtRelativeTime } from "../../utils/helpers.js";
import { notificationTone } from "../../utils/notifications.js";

export default function NotificationItem({ notification, onSelect }) {
  const { type, title, content, status, created_at: createdAt } = notification;
  const unread = status === "unread";

  return (
    <li className="notification-list-item">
      <button
        type="button"
        className={classNames(
          "notification-item",
          unread ? "is-unread" : "is-read",
          `tone-${notificationTone(type)}`
        )}
        onClick={() => onSelect(notification)}
      >
        <span className="notification-item-dot" aria-hidden="true" />

        <span className="notification-item-body">
          <span className="notification-item-head">
            <span className="notification-item-title">
              <span className="sr-only">{unread ? "Unread: " : "Read: "}</span>
              {title}
            </span>

            <time className="notification-item-time" dateTime={createdAt} title={fmtDate(createdAt)}>
              {fmtRelativeTime(createdAt)}
            </time>
          </span>

          {content ? <span className="notification-item-content">{content}</span> : null}
        </span>
      </button>
    </li>
  );
}
