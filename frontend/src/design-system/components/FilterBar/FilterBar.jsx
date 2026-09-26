import { ChevronDown, Plus } from "lucide-react";

/**
 * The global filter bar (Time range / Environment / Segment, etc). Applies to every panel
 * on the page it's rendered on. Filters are visual/inert for now — no page reads them yet —
 * so onClick handlers are optional; wire them once a page actually needs to filter by one.
 */
export function FilterBar({ chips, onAddFilter }) {
  return (
    <div className="filter-bar">
      <span className="filter-scope-label">Dashboard filters</span>
      {chips.map((chip) => (
        <FilterChip key={chip.label} {...chip} />
      ))}
      <button type="button" className="filter-add" onClick={onAddFilter}>
        <Plus aria-hidden="true" />
        Add filter
      </button>
    </div>
  );
}

export function FilterChip({ icon, label, value, isSet = false, onClick }) {
  return (
    <button type="button" className={`filter-chip${isSet ? " is-set" : ""}`} onClick={onClick}>
      {icon ? <span className="fc-icon">{icon}</span> : null}
      <span className="fc-label">{label}</span>
      <span className="fc-value">{value}</span>
      <ChevronDown className="fc-chevron" aria-hidden="true" />
    </button>
  );
}

/** A smaller chip scoped to a single panel (e.g. "Timeliness" on a dimension ranking, or a
 * time range that overrides the dashboard filter for one chart only). */
export function ComponentFilter({ children, title, onClick }) {
  return (
    <button type="button" className="component-filter" title={title} onClick={onClick}>
      {children}
      <ChevronDown aria-hidden="true" />
    </button>
  );
}

export default FilterBar;
