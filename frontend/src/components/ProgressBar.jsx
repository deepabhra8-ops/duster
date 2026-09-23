/**
 * ProgressBar.jsx - compact horizontal progress bar for table rows
 * (percentage fill + numeric label). Generic/reusable - first used by
 * ProfileMapper.jsx's jobs table (see docs/ux-plan.md §5).
 */
export default function ProgressBar({ percent = 0, colorVar = "--blue" }) {
  const clamped = Math.max(0, Math.min(100, percent));

  return (
    <div className="progress-bar" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar-track">
        <div className="progress-bar-fill" style={{ width: `${clamped}%`, background: `var(${colorVar})` }} />
      </div>
      <span className="progress-bar-label">{clamped}%</span>
    </div>
  );
}
