/**
 * RefreshButton.jsx - the per-page refresh control, AWS-console style.
 *
 * An icon-only button plus a "last updated" stamp. Pages render list data from
 * a sessionStorage cache (utils/pageCache.js), so the stamp is what keeps that
 * honest: the user can see how old what they are looking at actually is, and
 * force a re-pull without reaching for F5.
 *
 * Composition is deliberately the same as the Connections table's Edit button -
 * `btn btn-ghost btn-sm btn-icon-only` wrapping a masked `.btn-icon` span - so
 * this inherits the existing sizing, focus ring and disabled treatment rather
 * than introducing a second button idiom. The icon is masked and painted with
 * currentColor, which is also why spinning it works: the mask rotates with the
 * element.
 *
 * Only rendered on pages that have a cache to invalidate. The job results pages
 * poll on their own every 1400 ms and cache nothing, so a button there would
 * duplicate what is already happening automatically.
 */
import { useEffect, useState } from "react";

import { fmtRelativeTime } from "../utils/helpers.js";

/** Re-render the stamp about as often as its text can change. */
const TICK_MS = 30_000;

/**
 * @param {"left"|"right"} stampSide  Which side of the icon the "Updated ..."
 *   text sits on. Default "left" suits a toolbar, where the control is the last
 *   thing in the row and the stamp reads as a lead-in to it. "right" suits a
 *   page heading, where the button belongs against the title and the stamp
 *   trails it.
 */
export default function RefreshButton({
  onRefresh,
  refreshing = false,
  lastUpdated = null,
  label = "Refresh",
  stampSide = "left",
}) {
  // lastUpdated is a fixed instant, but "2 minutes ago" is not - without a tick
  // the stamp would freeze at whatever it said when the data arrived.
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
