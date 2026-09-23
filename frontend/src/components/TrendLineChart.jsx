import React, { useState } from 'react';

const pointDate = (p) => p.date || p.day || '';

export default function TrendLineChart({ points }) {
  const [hovered, setHovered] = useState(null);

  if (!points || points.length === 0) return null;

  const scores = points.map(p => Number(p.score) || 0);
  let min = Math.min(...scores);
  let max = Math.max(...scores);
  let span = max - min;
  
  if (span === 0) {
    min = Math.max(0, min - 0.01);
    max = Math.min(1, max + 0.01);
    span = max - min;
    if (span === 0) {
      min = 0; max = 1; span = 1;
    }
  } else {
    const pad = span * 0.1;
    min = Math.max(0, min - pad);
    max = Math.min(1, max + pad);
    span = max - min;
  }

  let decimals = 1;
  const stepDiff = (span * 0.25) * 100; 
  if (stepDiff > 0 && stepDiff < 0.1) decimals = 2;
  if (stepDiff > 0 && stepDiff < 0.01) decimals = 3;

  const steps = [1, 0.75, 0.5, 0.25, 0];
  
  const parseDate = (dString) => {
    if (!dString) return '';
    const dateStr = dString.split('T')[0];
    const [y, m, d] = dateStr.split('-');
    if (!y || !m || !d) return dString;
    const date = new Date(y, m - 1, d);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const maxLabels = 6;
  const labelIndices = new Set();
  if (points.length <= maxLabels) {
    points.forEach((_, i) => labelIndices.add(i));
  } else {
    labelIndices.add(0);
    labelIndices.add(points.length - 1);
    const innerCount = maxLabels - 2;
    for (let j = 1; j <= innerCount; j++) {
      labelIndices.add(Math.floor((points.length - 1) * (j / (innerCount + 1))));
    }
  }

  const polylineCoords = points.map((p, i) => {
    const x = points.length === 1 ? 50 : (i / (points.length - 1)) * 100;
    const y = 100 - (((Number(p.score) || 0) - min) / span) * 100;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div className="trend-line-chart-wrapper">
      <div className="trend-y-axis">
        {steps.map((step, i) => {
          const val = min + (span * step);
          return (
            <div key={i} className="trend-y-label-row" style={{ height: i === 0 || i === steps.length - 1 ? 'auto' : '0' }}>
              <span className="trend-y-label">{(val * 100).toFixed(decimals)}%</span>
            </div>
          );
        })}
      </div>
      <div className="trend-chart-content">
        <div className="trend-grid">
          {steps.map((step, i) => (
             <div key={i} className="trend-grid-line" style={{ top: `${(1 - step) * 100}%` }}></div>
          ))}
        </div>
        
        <div className="trend-data-area">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="trend-svg">
            <polyline
              points={polylineCoords}
              fill="none"
              stroke="var(--blue2)"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          
          {points.map((p, i) => {
            const x = points.length === 1 ? 50 : (i / (points.length - 1)) * 100;
            const y = 100 - (((Number(p.score) || 0) - min) / span) * 100;
            const runs = Number(p.runs) || 0;

            return (
              <div
                key={i}
                className={`trend-point${hovered === i ? ' is-hovered' : ''}`}
                style={{ left: `${x}%`, top: `${y}%` }}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              >
                <div className="trend-dot" />

                {hovered === i && (
                  <div
                    className={`trend-tooltip${x > 70 ? ' align-right' : ''}${x < 30 ? ' align-left' : ''}`}
                  >
                    <div className="tooltip-title">{parseDate(pointDate(p))}</div>
                    <div className="tooltip-row">
                      <span className="tooltip-status">DQ score</span>
                      <span className="tooltip-count">
                        {((Number(p.score) || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="tooltip-row">
                      <span className="tooltip-status">Runs</span>
                      <span className="tooltip-count">{runs}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        
        <div className="trend-x-axis">
          {points.map((p, i) => {
             if (!labelIndices.has(i)) return null;
             const x = points.length === 1 ? 50 : (i / (points.length - 1)) * 100;
             return (
               <div key={i} className="trend-x-label-container" style={{ left: `${x}%` }}>
                 <span className="trend-x-label">{parseDate(pointDate(p))}</span>
               </div>
             );
          })}
        </div>
      </div>
    </div>
  );
}
