/**
 * jobStatus.js - shared status vocabulary for a real backend job row (both
 * step "1" Profile Mapper and step "3" DQ Validator jobs use the same set -
 * see job_service.py's list_jobs/get_job), used by ProfileMapper.jsx and
 * Validator.jsx's jobs tables.
 */

/* One colour per status, defined once as --status-<name> in global.css. The pill
   class, the progress bar and the dashboard chart all read that same variable,
   so a status is the identical colour everywhere. */

/** .pill-status-* class (see app-chrome.css) per job status. */
export const STATUS_PILL = {
  draft: "pill-status-draft",
  queued: "pill-status-queued",
  running: "pill-status-running",
  cancelling: "pill-status-cancelling",
  done: "pill-status-done",
  error: "pill-status-error",
  cancelled: "pill-status-cancelled",
};

/** CSS variable per job status - ProgressBar's colorVar prop and the chart's segment fill. */
export const STATUS_PROGRESS_COLOR = {
  draft: "--status-draft",
  queued: "--status-queued",
  running: "--status-running",
  cancelling: "--status-cancelling",
  done: "--status-done",
  error: "--status-error",
  cancelled: "--status-cancelled",
};

/** Statuses a job still needs re-polling for (see each page's silent-polling effect). */
export const ACTIVE_STATUSES = ["queued", "running", "cancelling"];
