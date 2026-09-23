import React, { useState } from "react";

import StatusPill from "./StatusPill.jsx";
import { STATUS_PROGRESS_COLOR } from "../constants/jobStatus.js";
import { jobStatusLabel } from "../utils/helpers.js";

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

const NICE_STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

function niceMax(maxTotal) {
  if (maxTotal <= 4) return 4;

  const rough = maxTotal / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalised = rough / magnitude;

  let step = (NICE_STEPS.find((candidate) => candidate >= normalised) ?? 10) * magnitude;

  if (magnitude < 10) step = Math.max(1, Math.ceil(step));

  return step * 4;
}

export default function JobStatusChart({ profilingData = {}, validationData = {} }) {
  const [hoveredRow, setHoveredRow] = useState(null);

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
