export function scoreBucket(score) {
  if (score === null || score === undefined) return null;
  if (score >= 90) return "good";
  if (score >= 70) return "warn";
  return "bad";
}

export const SCORE_BADGE_CLASS = {
  good: "score-good",
  warn: "score-warn",
  bad: "score-bad",
};

export const SCORE_BAR_COLOR_VAR = {
  good: "var(--success)",
  warn: "var(--warning)",
  bad: "var(--danger)",
};
