import { Link } from "react-router-dom";
import { ResolveActions } from "../ResolveActions/ResolveActions.jsx";
import { scoreColorVar } from "../ScoreBadge/ScoreBadge.variants.js";

/**
 * rows: [{ id, name, score, deltaLabel, deltaDirection, href }]
 */
export function RankingRow({ name, score, deltaLabel, deltaDirection, href }) {
  const color = scoreColorVar(score);
  const deltaColor = deltaDirection === "down" ? "var(--danger)" : "var(--success)";
  const arrow = deltaDirection === "down" ? "▼" : "▲";

  return (
    <div className="rank-row">
      <Link to={href} className="rank-link">
        <span className="rank-name">{name}</span>
        <span className="score-bar-track" style={{ flex: 1 }}>
          <span className="score-bar-fill" style={{ width: `${Math.round(score)}%`, background: color }} />
        </span>
        <span className="ds-mono" style={{ fontSize: 12, color, width: 22 }}>
          {Math.round(score)}
        </span>
        {deltaLabel ? (
          <span className="rank-delta" style={{ color: deltaColor }}>
            {arrow} {deltaLabel}
          </span>
        ) : null}
      </Link>
      <ResolveActions lineageHref={href} />
    </div>
  );
}

export function RankingPanel({ rows }) {
  return (
    <div className="panel-body-flush">
      {rows.map((row) => (
        <RankingRow key={row.id} {...row} />
      ))}
    </div>
  );
}

export default RankingPanel;
