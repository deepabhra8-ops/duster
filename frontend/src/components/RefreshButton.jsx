import { useEffect, useState } from "react";

import { fmtRelativeTime } from "../utils/helpers.js";

const TICK_MS = 30_000;

export default function RefreshButton({
  onRefresh,
  refreshing = false,
  lastUpdated = null,
  label = "Refresh",
  stampSide = "left",
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!lastUpdated) return undefined;
    const id = setInterval(() => setTick((n) => n + 1), TICK_MS);
    return () => clearInterval(id);
  }, [lastUpdated]);

  const stamp = lastUpdated ? fmtRelativeTime(lastUpdated) : "";

  const stampEl = stamp ? (
    <span className="refresh-stamp" aria-live="polite">
      Updated {stamp}
    </span>
  ) : null;

  return (
    <div className="refresh-control">
      {stampSide === "left" ? stampEl : null}

      <button
        type="button"
        className={`btn btn-ghost btn-sm btn-icon-only${refreshing ? " btn-busy" : ""}`}
        onClick={onRefresh}
        disabled={refreshing}
        aria-label={label}
        title={label}
      >
        <span
          className={`btn-icon${refreshing ? " btn-icon-spinning" : ""}`}
          style={{ "--icon-src": "url(/icons/refresh.svg)" }}
          aria-hidden="true"
        />
      </button>

      {stampSide === "right" ? stampEl : null}
    </div>
  );
}
