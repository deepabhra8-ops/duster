/**
 * The Tier-2 tabs for the Quality rules section. Only "Rules" and "Runs" have real pages
 * today; "Templates" (a browsable view of the registry in ruleRegistry.js) is visible but
 * disabled, matching how other sections surface their full planned scope early.
 */
export const QUALITY_RULES_SECTION_TABS = [
  { label: "Rules", to: "/quality-rules" },
  { label: "Templates", disabled: true },
  { label: "Runs", to: "/quality-rules/runs" },
];
