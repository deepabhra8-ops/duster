const TIMESTAMP_RE = /^(\[\d{2}:\d{2}:\d{2}\])\s*([\s\S]*)$/;

const PATH_RE = /[A-Za-z]:\\[^:\r\n]+|\/(?:[^\s:/]+\/)+[^\s:/]*/g;

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

export function isTracebackMessage(message) {
  return (
    message.includes("Traceback (most recent call last)") ||
    /(^|\n)\s*File "/.test(message)
  );
}

export function isErrorLine(rawLine) {
  return rawLine.includes("❌") || rawLine.includes("ERROR") || isTracebackMessage(rawLine);
}

function stripPaths(text) {
  return text
    .replace(CONN_STRING_RE, "[connection string redacted]")
    .replace(PATH_RE, "")
    .replace(/\s+:/g, ":")
    .replace(/\s{2,}/g, " ")
    .trim();
}

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

  return [timestamp, stripPaths(message)].filter(Boolean).join(" ");
}

export function humanizeLog(lines = []) {
  return lines.map(humanizeLogLine);
}
