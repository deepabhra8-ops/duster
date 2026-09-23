import { fmtPct } from "../utils/helpers.js";

const CX = 80;
const CY = 64;
const R = 56;
const STROKE = 10;
const SEGMENTS = 48;

function pointAt(t) {
  const angle = (180 - t * 180) * (Math.PI / 180);
  return { x: CX + R * Math.cos(angle), y: CY - R * Math.sin(angle) };
}

const TRACK_POINTS = Array.from({ length: SEGMENTS + 1 }, (_, i) => pointAt(i / SEGMENTS));

function toPath(points) {
  return "M " + points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" L ");
}

const TRACK_PATH = toPath(TRACK_POINTS);

export default function ScoreGauge({ score, loading = false }) {
  const t = Math.max(0, Math.min(1, Number(score) || 0));

  const fillEndIndex = Math.round(t * SEGMENTS);
  const fillPoints = TRACK_POINTS.slice(0, fillEndIndex + 1);
  const fillPath = fillPoints.length > 1 ? toPath(fillPoints) : null;

  return (
    <svg
      className="score-gauge"
      viewBox="0 0 160 92"
      role="img"
      aria-label={loading ? "Score loading" : `Score: ${fmtPct(t, 0)}`}
      aria-busy={loading || undefined}
    >
      <defs>
        <linearGradient
          id="scoreGaugeGradient"
          gradientUnits="userSpaceOnUse"
          x1={CX - R}
          y1={CY}
          x2={CX + R}
          y2={CY}
        >
          <stop offset="0%" stopColor="var(--gauge-red)" />
          <stop offset="50%" stopColor="var(--gauge-yellow)" />
          <stop offset="100%" stopColor="var(--gauge-green)" />
        </linearGradient>
      </defs>

      <path d={TRACK_PATH} fill="none" stroke="var(--border2)" strokeWidth={STROKE} strokeLinecap="round" />

      {loading ? (
        <path
          className="score-gauge-sweep"
          d={TRACK_PATH}
          pathLength="100"
          fill="none"
          stroke="url(#scoreGaugeGradient)"
          strokeWidth={STROKE}
          strokeLinecap="round"
        />
      ) : (
        fillPath && (
          <path
            d={fillPath}
            fill="none"
            stroke="url(#scoreGaugeGradient)"
            strokeWidth={STROKE}
            strokeLinecap="round"
          />
        )
      )}

      <text x={CX - R} y={CY + 13} textAnchor="middle" className="score-gauge-endlabel">0%</text>
      <text x={CX + R} y={CY + 13} textAnchor="middle" className="score-gauge-endlabel">100%</text>

      {loading ? (
        <g className="score-gauge-dots" aria-hidden="true">
          {[-11, 0, 11].map((dx, index) => (
            <circle
              key={dx}
              cx={CX + dx}
              cy={CY - 12}
              r={3.5}
              style={{ animationDelay: `${index * 0.16}s` }}
            />
          ))}
        </g>
      ) : (
        <text x={CX} y={CY - 6} textAnchor="middle" className="score-gauge-value">{fmtPct(t, 0)}</text>
      )}
    </svg>
  );
}
