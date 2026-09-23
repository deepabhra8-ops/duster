import { SCORE_BADGE_CLASS, SCORE_BAR_COLOR_VAR, scoreBucket } from "./ScoreBadge.variants.js";

export function ScoreBadge({ score }) {
  const bucket = scoreBucket(score);
  if (!bucket) return <span className="ds-mono" style={{ color: "var(--ink-faint)" }}>&mdash;</span>;

  return (
    <span className={`score-badge ${SCORE_BADGE_CLASS[bucket]}`}>
      <span className="score-dot" />
      {Math.round(score)}
    </span>
  );
}

export function ScoreBar({ score }) {
  const bucket = scoreBucket(score);
  if (!bucket) return <span className="ds-mono" style={{ color: "var(--ink-faint)" }}>&mdash;</span>;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span className="score-bar-track">
        <span
          className="score-bar-fill"
          style={{ width: `${Math.round(score)}%`, background: SCORE_BAR_COLOR_VAR[bucket] }}
        />
      </span>
      <span className="ds-mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
        {Math.round(score)}
      </span>
    </span>
  );
}

export default ScoreBadge;
