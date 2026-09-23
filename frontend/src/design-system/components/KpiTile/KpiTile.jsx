export function KpiTile({ label, value, valueColor, delta }) {
  return (
    <div className="kpi-tile">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value-row">
        <span className="kpi-value" style={valueColor ? { color: valueColor } : undefined}>
          {value}
        </span>
        {delta ? (
          <span className={`kpi-delta ${delta.direction === "down" ? "kpi-delta-down" : "kpi-delta-up"}`}>
            {delta.direction === "down" ? "▼" : "▲"} {delta.label}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default KpiTile;
