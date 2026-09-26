/**
 * Client-side mirror of the backend template registry (backend/engine/quality/templates.py,
 * also served at GET /api/quality-rules/templates): each template’s dimension, level,
 * applicable type families and threshold shape, which the editor needs synchronously to
 * render the template grid and parameter form. Keep the two in step when adding a template.
 * Dry-run plans come from the backend planner (dryRunRule in services/qualityRulesService.js).
 */

export const TEMPLATES = [
  { id: "not_null", name: "not_null", dimension: "Completeness", level: "row" },
  { id: "not_blank", name: "not_blank", dimension: "Completeness", level: "row" },
  { id: "in_range", name: "in_range", dimension: "Validity", level: "row" },
  { id: "allowed_values", name: "allowed_values", dimension: "Validity", level: "row" },
  { id: "regex_match", name: "regex_match", dimension: "Validity", level: "row" },
  { id: "unique_ratio", name: "unique_ratio", dimension: "Uniqueness", level: "agg" },
  { id: "freshness_hours", name: "freshness_hours", dimension: "Timeliness", level: "agg" },
  { id: "row_count", name: "row_count", dimension: "Completeness", level: "table" },
  { id: "referential_integrity", name: "referential_integrity", dimension: "Consistency", level: "cross" },
  { id: "sql_row", name: "sql_row", dimension: "Custom SQL", level: "row" },
];

export const ALL_FAMILIES = ["numeric", "string", "temporal", "boolean", "binary", "complex"];

const FAMILIES_BY_TEMPLATE = {
  not_null: ALL_FAMILIES,
  not_blank: ["string"],
  in_range: ["numeric", "temporal"],
  allowed_values: ["string", "numeric"],
  regex_match: ["string"],
  unique_ratio: ["numeric", "string", "temporal"],
  freshness_hours: ["temporal"],
  row_count: [],
  referential_integrity: ["numeric", "string"],
  sql_row: ALL_FAMILIES,
};

const FAMILY_NOTE_BY_TEMPLATE = {
  not_null: "Any type.",
  row_count: "Table-level — binds once per table, not per column.",
  sql_row: "Any type. Narrow it if the expression needs one.",
};

const DEFAULT_FAMILY_NOTE = "Columns of other types are reported as skipped, with the reason.";

/** Which threshold-input shape (§3.3's metric/op/value) a template uses. */
const THRESHOLD_KIND_BY_TEMPLATE = {
  not_null: "passRateStrict",
  not_blank: "passRate",
  in_range: "passRate",
  allowed_values: "passRate",
  regex_match: "passRate",
  unique_ratio: "ratio",
  freshness_hours: "hoursMax",
  row_count: "rowsMin",
  referential_integrity: "passRateStrict",
  sql_row: "passRate",
};

export const SCOPE_LEVELS = ["column", "table", "schema", "catalog", "all"];

export function templateFamilies(templateId) {
  return FAMILIES_BY_TEMPLATE[templateId] || [];
}

export function templateFamilyNote(templateId) {
  return FAMILY_NOTE_BY_TEMPLATE[templateId] || DEFAULT_FAMILY_NOTE;
}

export function templateThresholdKind(templateId) {
  return THRESHOLD_KIND_BY_TEMPLATE[templateId] || "passRate";
}

const DEFAULT_THRESHOLD_BY_KIND = {
  passRate: { metric: "pass_rate", op: ">=", value: 99.0, unit: "%" },
  passRateStrict: { metric: "pass_rate", op: ">=", value: 100.0, unit: "%" },
  ratio: { metric: "value", op: ">=", value: 0.995, unit: "ratio" },
  hoursMax: { metric: "value", op: "<=", value: 24, unit: "hours" },
  rowsMin: { metric: "value", op: ">=", value: 1, unit: "rows" },
};

export function defaultThresholdForTemplate(templateId) {
  return DEFAULT_THRESHOLD_BY_KIND[templateThresholdKind(templateId)];
}

/** Starting parameters for a freshly-picked template, matching the mockup's per-template
 * defaults (§8.1's example values, e.g. in_range's 0/250000). */
export function defaultParamsForTemplate(templateId) {
  switch (templateId) {
    case "in_range":
      return { min: 0, max: 100, boundsInclusive: true };
    case "allowed_values":
      return { values: "USD, EUR, GBP, INR, JPY", matchCase: true };
    case "regex_match":
      return { pattern: "^[A-Z]{2}$", fullValue: true };
    case "unique_ratio":
      return { exact: false, maxRsd: 0.05 };
    case "freshness_hours":
      return { measuredAgainst: "current_timestamp()" };
    case "referential_integrity":
      return { parentTable: "main.sales.customers", parentColumn: "customer_id" };
    case "sql_row":
      return { expression: "{column} IS NULL OR {column} >= 0" };
    default:
      return {};
  }
}
