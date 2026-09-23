/**
 * helpers.js - Shared pure utilities.
 *
 * Ported from the vanilla utils.js. DOM-string helpers (innerHTML-based
 * alerts/pills/spinners) are intentionally dropped in favour of JSX in the
 * components; the framework-agnostic logic below is kept.
 */
import { SCORE_THRESHOLDS, SCORE_LEGEND } from "../constants/dqRules.js";

/** RAG class for a 0..1 score. */
export const scoreClass = (score) =>
  score >= SCORE_THRESHOLDS.GOOD ? "sc-good" : score >= SCORE_THRESHOLDS.WARNING ? "sc-warn" : "sc-bad";

/** "Good" / "Warning" / "Poor" label for a 0..1 score - same thresholds as scoreClass, via SCORE_LEGEND. */
export const scoreStatusLabel = (score) =>
  SCORE_LEGEND.find((entry) => entry.cls === scoreClass(score))?.label ?? "-";

/** .pill-* colour class (see global.css) matching a score's RAG class. */
const PILL_BY_SCORE_CLASS = { "sc-good": "pill-green", "sc-warn": "pill-amber", "sc-bad": "pill-red" };
export const scorePillClass = (score) => PILL_BY_SCORE_CLASS[scoreClass(score)];

/** --colour-var (see global.css :root) matching a score's RAG class - for ProgressBar's colorVar prop. */
const COLOR_VAR_BY_SCORE_CLASS = { "sc-good": "--green", "sc-warn": "--amber", "sc-bad": "--red" };
export const scoreColorVar = (score) => COLOR_VAR_BY_SCORE_CLASS[scoreClass(score)];

/** Format a 0..1 score as a percentage string (e.g. 0.937 → "93.7%"). */
export const fmtPct = (score, digits = 1) =>
  Number.isFinite(score) ? `${(score * 100).toFixed(digits)}%` : "-";

/** Human-readable byte size (e.g. 2048 → "2.0 KB"). */
export const fmtBytes = (bytes) => {
  if (!bytes) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${u[i]}`;
};

/** Locale-friendly date/time from an ISO string or epoch. */
export const fmtDate = (value) => {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
};

const RELATIVE_TIME = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/**
 * "just now" / "2 minutes ago" - the freshness stamp beside a refresh button.
 *
 * Complements fmtDate above, which is absolute. A relative stamp is what makes a
 * cached page honest: the user can see at a glance whether they are looking at
 * something from a second ago or from before lunch.
 */
export const fmtRelativeTime = (value) => {
  if (!value) return "";

  const then = value instanceof Date ? value.getTime() : new Date(value).getTime();
  if (Number.isNaN(then)) return "";

  const seconds = Math.round((then - Date.now()) / 1000);
  const magnitude = Math.abs(seconds);

  // Under a minute, "0 seconds ago" reads worse than plain English.
  if (magnitude < 45) return "just now";

  const units = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
  ];

  for (const [unit, size] of units) {
    if (magnitude < size * 60 || unit === "day") {
      return RELATIVE_TIME.format(Math.round(seconds / size), unit);
    }
  }

  return RELATIVE_TIME.format(Math.round(seconds / 86400), "day");
};

/** Trailing-edge debounce. Returns a function with a .cancel() method. */
export function debounce(fn, delay = 300) {
  let t;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

/** Join conditional class names: classNames("a", cond && "b") → "a b". */
export const classNames = (...parts) => parts.filter(Boolean).join(" ");

/**
 * Attach to a <form>'s onKeyDown to block the implicit Enter-to-submit a
 * real <form> gets from any single-line text <input> inside it - used by
 * NewValidatorJobModal.jsx and NewProfileMapperJobModal.jsx, both wrapped in
 * an actual <form> (see their header comments) but not meant to submit on
 * Enter. Scoped to INPUT specifically so Enter still does its normal job
 * elsewhere: inserting a newline in a <textarea> (Description), and
 * activating a focused <button> (Create) - neither of those goes through
 * this check, since their tagName isn't "INPUT".
 */
export const preventEnterSubmit = (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT") e.preventDefault();
};

/**
 * Human-readable label for a job status value - shared by ProfileMapper.jsx
 * and Validator.jsx's jobs tables (status pill + status filter dropdown) so
 * both read the same wording for the same status, rather than each page's
 * own ad-hoc text. Covers every status either page's real job model uses
 * (both are step "1"/"3" jobs off the same backend now - see job_service.py's
 * list_jobs); "running"/"done"/"error"/"cancelled" are the four originally
 * requested - "In-Progress" rather than "Running" to read as an ongoing
 * state, not just one verb among several. draft/queued/cancelling get a
 * plain title-cased label instead of being folded into one of the four.
 */
const JOB_STATUS_LABELS = {
  draft: "Draft",
  queued: "Queued",
  running: "In-Progress",
  cancelling: "Cancelling",
  done: "Completed",
  error: "Error",
  cancelled: "Cancelled",
};
export const jobStatusLabel = (status) => JOB_STATUS_LABELS[status] || status;

/**
 * Reword a POST /api/job/{id}/start failure (JobService.start_draft_job's state
 * guards - "Add at least one table before starting" / "Job is not a draft" - or a
 * plain "Job not found") into something a non-engineer can act on without reading
 * backend terminology. Falls back to the raw message unchanged when it doesn't
 * match a known case, so nothing is ever silently dropped. Shared by
 * ProfileMapper.jsx and Validator.jsx's own handleRun - same start endpoint,
 * same guards, same wording either page's job hits them from.
 */
export function friendlyStartError(message) {
  if (!message) return "Something went wrong while starting this job. Please try again.";
  if (/add at least one.*table/i.test(message)) {
    return "This job doesn't have a table or source file configured yet. Open it and add at least one before running.";
  }
  if (/select a source file/i.test(message)) {
    return "One of this job's tables is missing its source file - attach a file before running.";
  }
  if (/not a draft/i.test(message)) {
    return "This job has already been started and can't be run again from here.";
  }
  if (/job not found/i.test(message)) {
    return "This job no longer exists - try refreshing the page.";
  }
  return message;
}

/** Open a URL in a new tab (used for backend file downloads). */
export const openInNewTab = (url) => {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
};
