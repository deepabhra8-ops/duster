/**
 * humanizeLog.js - Turn raw backend job-log lines into short, human-readable
 * status messages.
 *
 * job_service._log_job() timestamps whatever pipeline_service.py hands it,
 * which currently includes internal server file paths (the "→ {path}"
 * lines from config/profile-map/report/staging writes) and, on failure,
 * the raw exception text plus a full traceback.format_exc() dump as a
 * single log entry - occasionally including a DB connection string with
 * an embedded plaintext password, since some DB drivers echo the DSN back
 * in their error text. That's fine for a developer tailing a log file, but
 * it's confusing/unprofessional (and in the credentials case, a real leak)
 * shown verbatim to an end user watching a job run - so this maps each
 * line to plain-language copy and strips filesystem paths, connection
 * strings, and stack-trace content before it's ever rendered.
 */

const TIMESTAMP_RE = /^(\[\d{2}:\d{2}:\d{2}\])\s*([\s\S]*)$/;

/**
 * Absolute filesystem paths, anywhere in a message:
 *   - Windows: "D:\DQ Validator\..." - directory names can contain
 *     spaces, so this consumes everything from the drive letter up to the
 *     next colon/newline (a colon can't appear in a Windows path itself).
 *   - POSIX: "/home/app/..." - at least two "/"-separated segments, so a
 *     lone "/" (e.g. in "pass/fail") isn't treated as a path.
 */
const PATH_RE = /[A-Za-z]:\\[^:\r\n]+|\/(?:[^\s:/]+\/)+[^\s:/]*/g;

/**
 * Database connection strings with embedded credentials, e.g.
 * "postgresql+psycopg2://user:pass@host:5432/db" - connection_service.py
 * builds these with the plaintext password inline, and DB drivers commonly
 * echo the DSN back in their exception text.
 */
const CONN_STRING_RE = /\b[a-zA-Z][\w+-]*:\/\/[^\s@]+:[^\s@]+@[^\s/]+(?:\/[^\s]*)?/g;

const FRIENDLY_RULES = [
  { test: /^Job started$/, text: "🚀 Job started" },
  { test: /^Config written/, text: "⚙️ Configuration prepared" },
  { test: /^Running Step 1/, text: "🔍 Analyzing source structure (Profile Mapper)…" },
  { test: /^Profile Map saved/, text: "✅ Profile map generated" },
  { test: /^Running Step 3/, text: "🔎 Running data quality checks…" },
  { test: /^DQ Report saved/, text: "✅ Data quality report ready" },
  { test: /^Staging output/, text: "✅ Clean data staged" },
  { test: /^Job complete$/, text: "🎉 Job complete" },
];

/** True for a raw exception/stack-trace dump (traceback.format_exc() output). */
export function isTracebackMessage(message) {
  return (
    message.includes("Traceback (most recent call last)") ||
    /(^|\n)\s*File "/.test(message)
  );
}

/** True for any raw line that represents a failure, for severity styling. */
export function isErrorLine(rawLine) {
  return rawLine.includes("❌") || rawLine.includes("ERROR") || isTracebackMessage(rawLine);
}

function stripPaths(text) {
  return text
    .replace(CONN_STRING_RE, "[connection string redacted]")
    .replace(PATH_RE, "")
    .replace(/\s+:/g, ":") // "open : denied" → "open: denied"
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Convert one raw "[HH:MM:SS] message" log line into user-facing text. */
export function humanizeLogLine(rawLine) {
  const match = TIMESTAMP_RE.exec(rawLine);
  const timestamp = match ? match[1] : "";
  const message = match ? match[2] : rawLine;

  if (isTracebackMessage(message)) {
    return [timestamp, "❌ An internal error occurred. Please contact your administrator if this keeps happening."]
      .filter(Boolean)
      .join(" ");
  }

  const errorMatch = /^ERROR:\s*([\s\S]*)$/.exec(message);
  if (errorMatch) {
    const cleaned = stripPaths(errorMatch[1]);
    return [timestamp, `❌ Job failed${cleaned ? `: ${cleaned}` : "."}`].filter(Boolean).join(" ");
  }

  const rule = FRIENDLY_RULES.find((r) => r.test.test(message));
  if (rule) return [timestamp, rule.text].filter(Boolean).join(" ");

  // Fallback for any line we don't specifically recognize: still strip raw
  // filesystem paths so unanticipated future log lines can't leak them either.
  return [timestamp, stripPaths(message)].filter(Boolean).join(" ");
}

/** Humanize a full array of raw job-log lines, in order. */
export function humanizeLog(lines = []) {
  return lines.map(humanizeLogLine);
}
