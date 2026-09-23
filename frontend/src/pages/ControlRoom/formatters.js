import { fmtRelativeTime, jobStatusLabel } from "../../utils/helpers.js";

const JOB_STATUS_TONE = {
  draft: "neutral",
  queued: "neutral",
  running: "data",
  cancelling: "warning",
  done: "success",
  error: "danger",
  cancelled: "neutral",
};

export function jobStatusTone(status) {
  return JOB_STATUS_TONE[status] || "neutral";
}

export function jobStatusText(status) {
  return jobStatusLabel(status);
}

export function jobTypeLabel(step) {
  return String(step) === "3" ? "validator" : "profile-mapper";
}

export function jobStartedLabel(startedIso) {
  if (!startedIso) return "—";
  return fmtRelativeTime(startedIso);
}

/**
 * Computes an up/down delta label from the last two points of a 7-day score_trend series.
 * Returns null when there's no real comparison period, per the KpiTile spec ("don't
 * fabricate a trend arrow for a tile with no history").
 */
export function scoreDelta(scoreTrend) {
  if (!Array.isArray(scoreTrend) || scoreTrend.length < 2) return null;

  const last = scoreTrend[scoreTrend.length - 1]?.score;
  const prev = scoreTrend[scoreTrend.length - 2]?.score;
  if (typeof last !== "number" || typeof prev !== "number" || prev === 0) return null;

  const diffPct = ((last - prev) / prev) * 100;
  if (!Number.isFinite(diffPct) || Math.round(diffPct) === 0) return null;

  return {
    direction: diffPct >= 0 ? "up" : "down",
    label: `${Math.abs(Math.round(diffPct))}%`,
  };
}

export function scoreColorVar(score) {
  if (typeof score !== "number") return undefined;
  if (score >= 90) return "var(--success)";
  if (score >= 70) return "var(--warning)";
  return "var(--danger)";
}
