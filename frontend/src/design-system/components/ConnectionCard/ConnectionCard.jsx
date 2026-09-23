import { StatusRow } from "../Badge/StatusDot.jsx";

const EM_DASH = "—";

function sourceGlyph(dbType) {
  return String(dbType || "").slice(0, 2).toUpperCase() || "??";
}

export function ConnectionCard({ name, host, dbType, statusTone = "idle", statusLabel, statusDetail, stats, onMenu }) {
  const { schemas = EM_DASH, tables = EM_DASH, avgScore = EM_DASH } = stats || {};

  return (
    <div className="conn-card">
      <div className="conn-card-head">
        <div className="conn-icon">{sourceGlyph(dbType)}</div>
        <div>
          <div className="conn-title">{name}</div>
          <div className="conn-sub">{host || EM_DASH}</div>
        </div>
        {onMenu ? (
          <button type="button" className="btn btn-ghost btn-icon conn-menu-btn" aria-label="More" onClick={onMenu}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="5" cy="12" r="1.4" />
              <circle cx="12" cy="12" r="1.4" />
              <circle cx="19" cy="12" r="1.4" />
            </svg>
          </button>
        ) : null}
      </div>

      <StatusRow tone={statusTone} label={statusLabel} detail={statusDetail} />

      <div className="conn-stats">
        <div>
          <div className="conn-stat-label">Schemas</div>
          <div className="conn-stat-value">{schemas}</div>
        </div>
        <div>
          <div className="conn-stat-label">Tables</div>
          <div className="conn-stat-value">{tables}</div>
        </div>
        <div>
          <div className="conn-stat-label">Avg score</div>
          <div className="conn-stat-value">{avgScore}</div>
        </div>
      </div>
    </div>
  );
}

export default ConnectionCard;
