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
