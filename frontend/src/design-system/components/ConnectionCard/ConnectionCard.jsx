import { Plus, RefreshCw, ExternalLink } from "lucide-react";
import { StatusRow } from "../Badge/StatusDot.jsx";
import { Button } from "../Button/Button.jsx";

const EM_DASH = "—";

const VARIANT_CLASS = {
  connected: "",
  warning: "is-warning",
  error: "is-error",
  syncing: "is-syncing",
  ghost: "is-ghost",
};

function sourceGlyph(dbType) {
  return String(dbType || "").toUpperCase() || "??";
}

/**
 * variant: "connected" (default) | "warning" | "error" | "syncing" | "ghost". Each variant
 * swaps the card's body content for the state a real connection can be in, per the
 * Connections mockup: connected/warning both show the schemas/tables/avg-score stat row
 * (warning only differs by its amber border + status label); error swaps the stats for an
 * explanation + a retry action; syncing swaps them for a live progress bar; ghost (not yet
 * connected) drops the status row entirely for a short description + a connect action.
 */
export function ConnectionCard({
  variant = "connected",
  name,
  host,
  dbType,
  statusTone = "idle",
  statusLabel,
  statusDetail,
  stats,
  onMenu,
  errorNote,
  onRetry,
  syncPercent,
  description,
  connectTo,
  connectDisabled,
}) {
  const { schemas = EM_DASH, tables = EM_DASH, avgScore = EM_DASH } = stats || {};
  const cardClass = ["conn-card", VARIANT_CLASS[variant]].filter(Boolean).join(" ");

  return (
    <div className={cardClass}>
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

      {variant !== "ghost" ? <StatusRow tone={statusTone} label={statusLabel} detail={statusDetail} /> : null}

      {variant === "error" ? (
        <>
          <div className="conn-error-note">{errorNote}</div>
          <button type="button" className="btn btn-secondary btn-xs" style={{ alignSelf: "flex-start" }} onClick={onRetry}>
            <RefreshCw size={12} aria-hidden="true" />
            Retry connection
          </button>
        </>
      ) : variant === "syncing" ? (
        <div className="conn-sync-row">
          <span className="score-bar-track" style={{ flex: 1 }}>
            <span className="score-bar-fill" style={{ width: `${syncPercent}%`, background: "var(--data)" }} />
          </span>
          <span className="conn-sync-label">{syncPercent}%</span>
        </div>
      ) : variant === "ghost" ? (
        <>
          <div className="conn-ghost-desc">{description}</div>
          <Button
            register="secondary"
            size="xs"
            style={{ alignSelf: "flex-start" }}
            to={connectDisabled ? undefined : connectTo}
            disabled={connectDisabled}
            title={connectDisabled ? "Coming soon" : undefined}
          >
            <ExternalLink size={12} aria-hidden="true" />
            {connectDisabled ? "Coming soon" : "Connect"}
          </Button>
        </>
      ) : (
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
      )}
    </div>
  );
}

/** The dashed "add a new item" tile that closes out a grid of cards (e.g. ConnectionCards). */
export function AddTile({ label = "Add connection", onClick }) {
  return (
    <button type="button" className="add-tile" onClick={onClick}>
      <Plus aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}

export default ConnectionCard;
