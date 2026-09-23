/**
 * ScoreGauge.jsx - simple semi-circular ("semi radial") progress chart.
 *
 * A plain progress ring bent into a half-circle: a flat grey track (same
 * `--border2` track colour ProgressBar.jsx uses) spans the full 0–100%
 * range, left end = 0%, right end = 100%, arcing over the top; a coloured
 * arc fills it from the left up to `score`. The fill's colour is read off
 * a fixed red -> yellow -> green scale positioned along that same range
 * (via a userSpaceOnUse gradient, so a given x position is always the same
 * colour regardless of how much of the arc is filled) - red/low, green/high
 * like the rest of the app's RAG colouring, just deliberately plain: no
 * needle, no dial ticks, no drop shadow. The three stops are `--gauge-red`
 * / `--gauge-yellow` / `--gauge-green` (global.css) - lighter siblings of
 * `--red`/`--yellow`/`--green` picked for this gradient specifically, since
 * those darker, muted tones (tuned as text colours elsewhere) read too flat
 * as a fill.
 *
 * A true semicircle (not stretched) - kept small and capped via
 * .score-gauge's max-width in global.css rather than filling the card's
 * full width, so it doesn't grow into an oversized dial on a wide card.
 *
 * Pure presentational: takes a 0..1 `score` and renders. No data fetching.
 */
import { fmtPct } from "../utils/helpers.js";

const CX = 80;
const CY = 64;
const R = 56;
const STROKE = 10;
const SEGMENTS = 48; // arc drawn as a many-segment polyline, not a single <path> arc command, so the gradient's stroke reads smoothly along the curve

// t: 0..1 -> point on the arc, sweeping left (0%) -> top (50%) -> right (100%)
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

  // Slice the same point set the track uses (rather than resampling) so the
  // fill's edge sits exactly on the track underneath it, with no seam.
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

      {/* Loading: one short arc segment sweeps the full track on a loop. It is
          stroked with the same position-based gradient the real fill uses, so
          the sweep shifts red -> yellow -> green as it travels - the gauge
          reads as "measuring" rather than as a score of zero. */}
      {loading ? (
        // pathLength normalizes the arc to 100 units, so the sweep's dash
        // pattern is expressible in plain numbers in the stylesheet. Animating
        // stroke-dashoffset against a calc(var(...)) of the real arc length
        // instead leaves Chrome unable to interpolate, and the dash sits frozen
        // at the final keyframe - invisible, past the end of the track.
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
        // Three dots where the percentage will land, so the value's slot is
        // already occupied and the number does not shift anything on arrival.
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
