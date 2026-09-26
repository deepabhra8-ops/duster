/**
 * The Tier-2 report-category tabs shared by every page under Dashboards. Only Dimensions
 * and Data sources have real pages today; the rest are visible-but-disabled so the full
 * category set (per the six-category report architecture) is legible even before it's
 * built out.
 */
export const DASHBOARD_SECTION_TABS = [
  { label: "Dimensions", to: "/dashboards/dimensions" },
  { label: "Critical elements", disabled: true },
  { label: "Business goals", disabled: true },
  { label: "Data sources", to: "/dashboards/data-sources" },
  { label: "Data consumers", disabled: true },
  { label: "Tickets", disabled: true },
];
