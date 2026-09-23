import { STATUS_DOT_TONES } from "./Pill.variants.js";

export function StatusDot({ tone = "idle", className = "" }) {
  const classes = ["status-dot", STATUS_DOT_TONES[tone], className].filter(Boolean).join(" ");
  return <span className={classes} aria-hidden="true" />;
}

export function StatusRow({ tone = "idle", label, detail }) {
  return (
    <span className="status-row">
      <StatusDot tone={tone} />
      {label}
      {detail ? <span className="status-label"> &middot; {detail}</span> : null}
    </span>
  );
}

export default StatusDot;
