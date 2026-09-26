import { GitBranch, Ticket, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * The Detect → Understand → Resolve row-level action cluster: View lineage, Create ticket,
 * Route to owner. Sits after a divider at the end of a triage row (ranking row, critical
 * data element row) so it reads as a distinct action zone, not more data.
 *
 * `lineageHref` navigates to the real drill-down when known; the other two actions have no
 * backend yet, so they're wired to `onCreateTicket`/`onRouteToOwner` no-ops until one exists.
 */
export function ResolveActions({ lineageHref, onCreateTicket, onRouteToOwner }) {
  return (
    <>
      <div className="row-divider" />
      <div className="row-actions">
        {lineageHref ? (
          <Link to={lineageHref} className="row-action-btn" title="View lineage" aria-label="View lineage">
            <GitBranch size={13} aria-hidden="true" />
          </Link>
        ) : null}
        <button type="button" className="row-action-btn" title="Create ticket" aria-label="Create ticket" onClick={onCreateTicket}>
          <Ticket size={13} aria-hidden="true" />
        </button>
        <button type="button" className="row-action-btn" title="Route to owner" aria-label="Route to owner" onClick={onRouteToOwner}>
          <UserPlus size={13} aria-hidden="true" />
        </button>
      </div>
    </>
  );
}

export default ResolveActions;
