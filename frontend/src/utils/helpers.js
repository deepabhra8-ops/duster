import { SCORE_THRESHOLDS, SCORE_LEGEND } from "../constants/dqRules.js";

export const scoreClass = (score) =>
  score >= SCORE_THRESHOLDS.GOOD ? "sc-good" : score >= SCORE_THRESHOLDS.WARNING ? "sc-warn" : "sc-bad";

export const scoreStatusLabel = (score) =>
  SCORE_LEGEND.find((entry) => entry.cls === scoreClass(score))?.label ?? "-";

const PILL_BY_SCORE_CLASS = { "sc-good": "pill-green", "sc-warn": "pill-amber", "sc-bad": "pill-red" };
export const scorePillClass = (score) => PILL_BY_SCORE_CLASS[scoreClass(score)];

const COLOR_VAR_BY_SCORE_CLASS = { "sc-good": "--green", "sc-warn": "--amber", "sc-bad": "--red" };
export const scoreColorVar = (score) => COLOR_VAR_BY_SCORE_CLASS[scoreClass(score)];

export const fmtPct = (score, digits = 1) =>
  Number.isFinite(score) ? `${(score * 100).toFixed(digits)}%` : "-";

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

export const fmtDate = (value) => {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
};

const RELATIVE_TIME = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export const fmtRelativeTime = (value) => {
  if (!value) return "";

  const then = value instanceof Date ? value.getTime() : new Date(value).getTime();
  if (Number.isNaN(then)) return "";

  const seconds = Math.round((then - Date.now()) / 1000);
  const magnitude = Math.abs(seconds);

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

export function debounce(fn, delay = 300) {
  let t;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export const classNames = (...parts) => parts.filter(Boolean).join(" ");

export const preventEnterSubmit = (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT") e.preventDefault();
};

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

export const openInNewTab = (url) => {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
};
