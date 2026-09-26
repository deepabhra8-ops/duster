/**
 * The shell for one of the five observability pillars (Freshness, Volume, Distribution,
 * Schema changes, Lineage impact) on the Data Sources drill-down. Each pillar's body is
 * bespoke — passed as children — since a tick row, a bar chart, and a lineage chain don't
 * share enough shape to be worth a shared body component.
 */
export function PillarCard({ icon, title, action, flex, children }) {
  return (
    <div className="pillar-card" style={flex ? { flex: "1 1 auto", minHeight: 0 } : undefined}>
      <div className="pillar-head">
        <span className="pillar-icon">{icon}</span>
        <span className="pillar-title">{title}</span>
        {action}
      </div>
      <div className="pillar-body">{children}</div>
    </div>
  );
}

export default PillarCard;
