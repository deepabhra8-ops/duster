/**
 * dqRules.js - The 11 Data Quality rule definitions (DQ1–DQ11) and
 * score thresholds, used by the Rule Reference page and scoring helpers.
 *
 * `params` is documentation shown to analysts, so it has to describe what the
 * engine's rule classes actually parse (backend/engine/rules/dq*.py), not what
 * an earlier implementation did. Several entries were inherited from a
 * pre-Spark version and described behaviour that no longer exists - corrected
 * against the implementations.
 */

export const DQ_RULES = [
  { id: "DQ1", dim: "Completeness", cat: "Null / Blank Check", desc: "Flags missing or empty values in mandatory columns", params: "-", pill: "pill-blue", example: { parameter: "-", input: "Customer email: (blank)", output: "Fail — mandatory columns cannot be null, empty, or whitespace-only. \"jane@example.com\" would pass.", note: "No parameter needed - mark a column mandatory in the job's rule configuration and this rule flags any row where it is null, an empty string, or only whitespace." } },
  { id: "DQ2", dim: "Conformity", cat: "Date Format", desc: "Verifies date or timestamp fields match a configured Python format", params: "%Y-%m-%d", pill: "pill-teal", example: { parameter: "%d-%m-%Y", input: "15-01-2020", output: "Pass — the date matches dd-mm-yyyy.", note: "Formats: %d-%m-%Y → 15-01-2020; %Y-%d-%m → 2020-15-01; %Y-%m-%d → 2020-01-15; %d/%m/%Y → 15/01/2020; %m/%d/%Y → 01/15/2020; %d %b %Y → 15 Jan 2020; %d %B %Y → 15 January 2020; %B %d, %Y → January 15, 2020; %b %d, %Y → Jan 15, 2020. Timestamp: %d-%m-%Y %H:%M:%S → 15-01-2020 14:30:45." } },
  { id: "DQ3", dim: "Conformity", cat: "String Length", desc: "Enforces min/max character length on string columns", params: "min | max", pill: "pill-teal", example: { parameter: "3 | 10", input: "Customer code: AB12", output: "Pass — 4 characters is between 3 and 10.", note: "Values shorter than 3 or longer than 10 fail. Spaces at the start and end are ignored." } },
  { id: "DQ4", dim: "Conformity", cat: "Decimal Precision", desc: "Checks decimal scale does not exceed configured precision", params: "precision", pill: "pill-teal", example: { parameter: "2", input: "Amount: 125.50", output: "Pass — it has 2 decimal places. 125.505 would fail.", note: "Decimal precision here means the maximum number of digits after the decimal point, not the total number of digits in the number." } },
  { id: "DQ5", dim: "Conformity", cat: "Range Validation", desc: "Validates numeric or date values within a defined range", params: "min_val | max_val", pill: "pill-teal", example: { parameter: "01-01-2020 | 31-12-2020", input: "Order date: 15-06-2020", output: "Pass — the date is within the configured inclusive range.", note: "For date ranges, enter dates consistently as dd-mm-yyyy. A date before 01-01-2020 or after 31-12-2020 fails." } },
  { id: "DQ6", dim: "Conformity", cat: "Value Validation", desc: "Exact match or %-wildcard match (case-insensitive)", params: "expected", pill: "pill-teal", example: { parameter: "Active", input: "Status: Inactive", output: "Fail — exact matching accepts only Active (ignoring case and surrounding spaces).", note: "Use % as a wildcard: %abc matches values ending in abc (for example, 123abc); abc% matches values starting in abc (abc123); %abc% matches values containing abc (xxabcxx)." } },
  { id: "DQ7", dim: "Conformity", cat: "Pattern / Regex", desc: "Validates values against a full-match regular expression", params: "regex", pill: "pill-teal", example: { parameter: "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", input: "Email: analyst@example.com", output: "Pass — the complete value matches the email pattern.", note: "Copy a pattern as the parameter. US phone: ^\\d{3}-\\d{3}-\\d{4}$ (555-123-4567). US SSN: ^\\d{3}-\\d{2}-\\d{4}$ (123-45-6789). Email: ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$. The whole value must match, not only one part of it." } },
  { id: "DQ8", dim: "Consistency", cat: "LOV / Reference Data", desc: "Looks up values against an uploaded List of Values", params: "lov_name", pill: "pill-amber", example: { parameter: "tablename.Gender", input: "Gender: Non-binary", output: "Pass — Non-binary is in the gender_values list.", note: "Use an LOV when a field has a controlled set of permitted values (an enum), such as Gender: Male, Female, Non-binary; or Status: Active, Inactive, Pending. Upload or configure the named list before running the rule." } },
  { id: "DQ9", dim: "Consistency", cat: "FK Integrity", desc: "Cross-table foreign-key existence validation", params: "ref_table | ref_col", pill: "pill-amber", example: { parameter: "customer_master | customer_id", input: "orders.customer_id: C1001", output: "Pass — C1001 exists in customer_master.customer_id.", note: "Select both the table being checked and its master/reference table in the job configuration. For example, check orders.customer_id against the customer_id column in customer_master. A value absent from the master table fails." } },
  { id: "DQ10", dim: "Uniqueness", cat: "Duplicate Detection", desc: "Duplicate check for one field or a combination of fields", params: "col1, col2, ...", pill: "pill-green", example: { parameter: "Single field: customer_id (no additional parameter if the selected rule column is customer_id). Composite: first_name,last_name,date_of_birth", input: "Two rows with the same first_name, last_name and date_of_birth", output: "Fail — both rows are duplicate composite keys.", note: "Use a single field to ensure, for example, every customer_id is unique. Use a comma-separated list for a composite key when uniqueness depends on several fields." } },
  { id: "DQ11", dim: "Custom", cat: "Custom Expression", desc: "Spark SQL boolean expression, optionally scoped by a filter expression", params: "filter_expr | row_expr", pill: "pill-red", example: { parameter: "country = 'India' | createddate < updateddate", input: "country = India, createddate = 01-01-2024, updateddate = 02-01-2024", output: "Pass — the row is in India and its created date is earlier than its updated date.", note: "The engine first filters with the expression before |. Only those rows are evaluated by the expression after |. India rows where createddate is not earlier than updateddate fail; rows from other countries are outside this check and pass." } },
];

/**
 * URL segment for a dimension name: "Completeness" -> "completeness".
 * The Rule Reference route (/rules/:dimension) and the second-tier sidebar
 * both build links from this, so a slug means the same thing everywhere.
 */
export function dimensionSlug(dimension) {
  return String(dimension)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    // Runs are already collapsed to a single dash above, so at most one can
    // sit at each end - no need for a quantifier here.
    .replace(/^-|-$/g, "");
}

/** Distinct dimension names in a rule list, alphabetical. */
export function ruleDimensions(rules) {
  return Array.from(new Set(rules.map((rule) => rule.dim))).sort((a, b) => a.localeCompare(b));
}

/** Score thresholds used for RAG colouring (GOOD ≥ .95, WARNING ≥ .80). */
export const SCORE_THRESHOLDS = { GOOD: 0.95, WARNING: 0.8 };

/**
 * Legend rows describing the score thresholds, for the Rule Reference page.
 * Each entry: { label, cls, range }
 */
export const SCORE_LEGEND = [
  { label: "Good", cls: "sc-good", range: "≥ 95%" },
  { label: "Warning", cls: "sc-warn", range: "80% – 94%" },
  { label: "Poor", cls: "sc-bad", range: "< 80%" },
];
