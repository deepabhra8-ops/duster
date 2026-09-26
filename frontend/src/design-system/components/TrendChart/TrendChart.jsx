/**
 * A composite trend line chart: a target threshold (dashed) plus a scored series with one
 * point flagged as an anomaly. Values are 0-100 scores; `anomalyIndex` marks the incident.
 */
export function TrendChart({ points, target, anomalyIndex, anomalyLabel, startLabel, endLabel }) {
  const w = 380;
  const h = 140;
  const padX = 10;
  const padTop = 10;
  const padBottom = 22;
  const min = 60;
  const max = 100;

  const toY = (score) => padTop + (1 - (score - min) / (max - min)) * (h - padTop - padBottom);
  const toX = (i) => padX + (i / (points.length - 1)) * (w - padX * 2);

  const coords = points.map((p, i) => [toX(i), toY(p)]);
  const line = coords.map((c) => c.join(",")).join(" ");
  const targetY = toY(target);

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Composite quality score trend">
      <line x1={0} y1={targetY} x2={w} y2={targetY} stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
      <text x={w - 2} y={targetY - 5} textAnchor="end" fontFamily="Inter, sans-serif" fontSize="9" fill="var(--ink-faint)">
        Target {target}
      </text>
      <polyline points={line} fill="none" stroke="var(--data)" strokeWidth="2" />
      {coords.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === anomalyIndex ? 4.5 : 2.5} fill={i === anomalyIndex ? "var(--danger)" : "var(--data)"} />
      ))}
      {anomalyIndex !== undefined && anomalyLabel ? (
        <text x={coords[anomalyIndex][0]} y={h - 8} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="9" fill="var(--danger)">
          {anomalyLabel}
        </text>
      ) : null}
      {startLabel ? (
        <text x={padX - 2} y={h - 8} fontFamily="Inter, sans-serif" fontSize="9" fill="var(--ink-faint)">
          {startLabel}
        </text>
      ) : null}
      {endLabel ? (
        <text x={w - padX + 2} y={h - 8} textAnchor="end" fontFamily="Inter, sans-serif" fontSize="9" fill="var(--ink-faint)">
          {endLabel}
        </text>
      ) : null}
    </svg>
  );
}

export default TrendChart;
