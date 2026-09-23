/**
 * JobStatusChart.jsx - "Jobs by Type" on the dashboard: one stacked bar per job
 * type (Validation, Profiling), split by execution status.
 *
 * Horizontal bars. They were upright columns before, and the note that replaced
 * the original horizontal pair argued the axis "runs the way a quantity is
 * usually read" - true, but with only two categories the column layout spent
 * most of the plot on empty space, and the two category names sat in a caption
 * strip under bars that were narrower than the words. Laid along the length of
 * the card, each bar gets the full width to differ in, and its name sits on the
 * same line as the thing it names.
 *
 * The legend is the same StatusPill the Profile Mapper and Validator job tables
 * use. A bar segment, the legend pill and the tables' progress bars all read the
 * same --status-* variable (global.css, mapped in constants/jobStatus.js), so a
 * status is the identical colour in every one of them.
 */
import React, { useState } from "react";

import StatusPill from "./StatusPill.jsx";
import { STATUS_PROGRESS_COLOR } from "../constants/jobStatus.js";
import { jobStatusLabel } from "../utils/helpers.js";

/* The fill for a status: its shared --status-* variable, or the neutral one for
   a status the app does not know. */
const statusFill = (status) => `var(${STATUS_PROGRESS_COLOR[status] || "--status-unknown"})`;

const STATUS_ORDER = [
  "done",
  "error",
  "cancelled",
  "running",
  "queued",
  "cancelling",
  "draft",
  "unknown",
];

const GRID_STEPS = [0, 0.25, 0.5, 0.75, 1];

const formatCompact = (num) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(num);

const formatNumber = (num) => new Intl.NumberFormat("en-US").format(num);

/* Step sizes a reader accepts as round, as multiples of a power of ten. The
   axis is always four of these, so every gridline lands on a whole number. */
const NICE_STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** The axis maximum: the smallest "round" value >= maxTotal, in four steps.
 *
 * The previous version rounded the LEADING DIGIT up, which meant a max of 111
 * became 200 - half the plot permanently empty, and both bars squeezed into the
 * left half where their difference is hardest to read. Choosing the STEP first
 * and multiplying by four gives 120 for the same data. */
function niceMax(maxTotal) {
  if (maxTotal <= 4) return 4;

  const rough = maxTotal / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalised = rough / magnitude;

  let step = (NICE_STEPS.find((candidate) => candidate >= normalised) ?? 10) * magnitude;

  // Below 10 a "nice" 1.5 or 2.5 step puts halves on the axis; whole numbers
  // only, since these are job counts.
  if (magnitude < 10) step = Math.max(1, Math.ceil(step));

  // Exactly four steps, because the gridlines are drawn at quarters of this
  // value. Returning the nearest multiple of `step` instead would let the max
  // be three or five steps, and the quarters then land between them - which is
  // how a max of 9 produced an axis reading 0, 2.25, 4.5, 6.75, 9.
  return step * 4;
}

export default function JobStatusChart({ profilingData = {}, validationData = {} }) {
  const [hoveredRow, setHoveredRow] = useState(null); // 'validation' | 'profiling' | null

  const validationTotal = Object.values(validationData).reduce((a, b) => a + b, 0);
  const profilingTotal = Object.values(profilingData).reduce((a, b) => a + b, 0);
  const roundedMax = niceMax(Math.max(validationTotal, profilingTotal, 1));

  const legendStatuses = STATUS_ORDER.filter(
    (status) => (profilingData[status] || 0) > 0 || (validationData[status] || 0) > 0
  );

  const renderRow = (data, total, label, id) => {
    const widthPercent = (total / roundedMax) * 100;

    return (
      <div
        className="hbar-row"
        key={id}
        onMouseEnter={() => setHoveredRow(id)}
        onMouseLeave={() => setHoveredRow(null)}
      >
        <span className="hbar-label" title={label}>{label}</span>

        <div className="hbar-track">
          <div className="hbar-stack" style={{ width: `${widthPercent}%` }}>
            {STATUS_ORDER.map((status) => {
              const count = data[status] || 0;
              if (count === 0) return null;
              // A share of THIS bar, not of the axis - the bar's own width
              // already carries the total.
              const share = total > 0 ? (count / total) * 100 : 0;
              return (
                <div
                  key={status}
                  className="hbar-segment"
                  style={{
                    width: `${share}%`,
                    backgroundColor: statusFill(status),
                  }}
                />
              );
            })}
          </div>

          {hoveredRow === id && total > 0 && (
            <div className="hbar-tooltip">
              <div className="tooltip-title">{label}</div>
              {STATUS_ORDER.map((status) => {
                const count = data[status] || 0;
                if (count === 0) return null;
                return (
                  <div key={status} className="tooltip-row">
                    <span
                      className="tooltip-swatch"
                      style={{ backgroundColor: statusFill(status) }}
                    />
                    <span className="tooltip-status">{jobStatusLabel(status)}</span>
                    <span className="tooltip-count">{formatNumber(count)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* The bar shows the split; this shows the size. Without it a reader has
            to measure the bar against the axis to answer "how many?". */}
        <span className="hbar-total">{formatCompact(total)}</span>
      </div>
    );
  };

  return (
    <div className="stacked-chart-container">
      <p className="section-desc hbar-desc">
        Validation and profiling jobs grouped by execution status.
      </p>

      <div className="stacked-chart-area hbar">
        <div className="hbar-plot">
          {/* One vertical rule per axis step, behind the bars. Inset to the
              track column so the rules start at the bars' zero, not at the
              card's edge. */}
          <div className="hbar-grid" aria-hidden="true">
            {GRID_STEPS.map((step, i) => (
              <div key={i} className="hbar-grid-line" />
            ))}
          </div>

          <div className="hbar-rows">
            {renderRow(validationData, validationTotal, "Validation", "validation")}
            {renderRow(profilingData, profilingTotal, "Profiling", "profiling")}
          </div>
        </div>

        <div className="hbar-axis" aria-hidden="true">
          {GRID_STEPS.map((step, i) => (
            <span key={i} className="hbar-axis-label">
              {formatCompact(Math.round(step * roundedMax))}
            </span>
          ))}
        </div>
      </div>

      {/* Pinned to the bottom of whatever height the card has. */}
      {legendStatuses.length > 0 && (
        <div className="stacked-chart-legend hbar-legend">
          {legendStatuses.map((status) => (
            <StatusPill key={status} status={status} />
          ))}
        </div>
      )}
    </div>
  );
}
