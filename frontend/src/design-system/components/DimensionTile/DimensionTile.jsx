import { Link } from "react-router-dom";
import { scoreColorVar } from "../ScoreBadge/ScoreBadge.variants.js";

/**
 * A KpiTile variant for a single data-quality dimension score, with a trend sparkline
 * (filled area + line + an end-point marker for "today") so a viewer can see whether the
 * dimension is improving or degrading, not just its current value.
 *
 * trend: array of numbers (oldest first), same scale as `score` (0-100).
 */
export function DimensionTile({ label, score, deltaLabel, deltaDirection, trend, to }) {
  const color = scoreColorVar(score);
  const deltaColor = deltaDirection === "down" ? "var(--danger)" : "var(--success)";
  const arrow = deltaDirection === "down" ? "▼" : "▲";

  const Tag = to ? Link : "div";
  const tagProps = to ? { to } : {};

  return (
    <Tag className="kpi-tile dim-tile" {...tagProps}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value-row">
        <span className="kpi-value" style={{ color, fontSize: 24 }}>
          {Math.round(score)}
        </span>
        {deltaLabel ? (
          <span className="kpi-delta" style={{ color: deltaColor }}>
            {arrow} {deltaLabel}
          </span>
        ) : null}
      </div>
      {trend?.length > 1 ? <Sparkline trend={trend} color={color} /> : null}
      <div className="dim-spark-caption">12-week trend</div>
    </Tag>
  );
}

function Sparkline({ trend, color }) {
  const w = 60;
  const h = 34;
  const min = Math.min(...trend);
  const max = Math.max(...trend);
  const span = max - min || 1;

  const points = trend.map((v, i) => {
    const x = (i / (trend.length - 1)) * w;
    const y = h - 4 - ((v - min) / span) * (h - 8);
    return [x, y];
  });

  const line = points.map((p) => p.join(",")).join(" ");
  const area = `${line} ${w},${h} 0,${h}`;
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg className="dim-spark" width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polygon points={area} fill={color} opacity="0.14" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r="2.6" fill={color} />
    </svg>
  );
}

export default DimensionTile;
