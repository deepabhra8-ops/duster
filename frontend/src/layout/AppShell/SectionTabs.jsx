import { NavLink } from "react-router-dom";

/**
 * The Tier-2 bar: contextual tabs for the current Tier-1 section. Each page renders its
 * own SectionTabs directly below TopBar, since the tab set differs per section (per the
 * Duster Console two-tier nav design — Tier 1 is the app shell, Tier 2 is section-local).
 *
 * items: [{ label, to, disabled? }]. `right` is an optional slot for page-level meta
 * (e.g. "Scored nightly · last run 6h ago") rendered at the end of the bar.
 */
export function SectionTabs({ items, right }) {
  return (
    <div className="section-tabs-bar">
      <div className="dtabs">
        {items.map((item) =>
          item.disabled ? (
            <span key={item.label} className="dtab is-disabled" title="Not available yet" aria-disabled="true">
              {item.label}
            </span>
          ) : (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) => `dtab${isActive ? " is-active" : ""}`}
            >
              {item.label}
            </NavLink>
          )
        )}
      </div>
      {right ? <div className="section-tabs-right">{right}</div> : null}
    </div>
  );
}

export default SectionTabs;
