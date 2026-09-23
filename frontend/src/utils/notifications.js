/**
 * notifications.js - small pure helpers for the notification bell.
 */

/**
 * True only for an in-app path such as "/validator/abc".
 *
 * Clicking a notification navigates to its link, so a link that could leave the app would
 * send a user wherever whoever created the row chose. The server refuses to store one, and
 * this checks again because the client is what actually navigates - it must not rely on
 * every row having come through that check. "//host" is protocol-relative, a backslash is
 * read as a slash by browsers, and browsers strip tabs/newlines from a URL, which would turn
 * "/<tab>/host" into "//host"; all three count as leaving.
 *
 * Mirrors backend/services/notification_service.py's is_internal_link.
 */
export function isInternalPath(link) {
  return (
    typeof link === "string" &&
    link.startsWith("/") &&
    !link.startsWith("//") &&
    !link.includes("\\") &&
    // eslint-disable-next-line no-control-regex -- refusing control characters is the point
    !/[\u0000-\u001f\u007f]/.test(link)
  );
}

/** Visual tone by notification type. Anything unrecognised is neutral, so a new type needs no UI change. */
const TONE_BY_TYPE = {
  job_done: "success",
  job_error: "error",
  job_cancelled: "warn",
  success: "success",
  error: "error",
  warning: "warn",
  info: "info",
};

export const notificationTone = (type) => TONE_BY_TYPE[type] || "info";
