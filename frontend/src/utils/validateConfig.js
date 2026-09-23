/**
 * validateConfig.js - Pre-flight validation for the pipeline configuration.
 *
 * Run before navigating from Configure → Run Pipeline so an incomplete/
 * invalid config (missing tables, missing connection details, an
 * unsupported run-mode/step combination, etc.) is caught up front instead
 * of only surfacing as a backend job failure.
 *
 * `profileMaps` (optional) is the list of uploaded profile-map filenames -
 * pass it when known (Configure has it) to catch a Step 3 run that has no
 * profile map selected *and* none available to fall back to. Leaving it
 * blank is otherwise a legitimate, backend-supported choice
 * (config_builder.py's _resolve_profile_map_path falls back to the job's
 * own generated map, then to any uploaded one), so this is skipped rather
 * than assumed-invalid when the list isn't available (e.g. from a Run page,
 * which doesn't fetch it).
 *
 * Returns an array of human-readable error messages; empty array = valid.
 */
import { SOURCE_TYPES } from "../constants/sourceTypes.js";
import { DB_FIELD_CONFIGS, DB_REQUIRED_FIELDS } from "../constants/dbFields.js";
import { STEPS } from "../constants/appConfig.js";

export function validateConfig(config, { profileMaps = null } = {}) {
  const errors = [];
  const isFlat = config.source_type === SOURCE_TYPES.FLAT_FILE;

  if (!String(config.project_name || "").trim()) {
    errors.push("Project name is required.");
  }

  if (Number(config.run_mode) === 2 && String(config.step) === STEPS.STEP1) {
    errors.push("Curation (Run Mode 2) doesn't support the Profile Mapper step - select DQ Validator (Step 3) instead.");
  }

  if (!isFlat) {
    const dbType = config.databaseType || "";
    if (!dbType) {
      errors.push("Select a database type.");
    } else {
      const details = config.connectionDetails || {};
      const required = DB_REQUIRED_FIELDS[dbType] || [];
      const missing = required.filter((f) => !String(details[f] ?? "").trim());
      if (missing.length) {
        const labels = (DB_FIELD_CONFIGS[dbType] || [])
          .filter((f) => missing.includes(f.id))
          .map((f) => f.label);
        errors.push(`Database connection is missing: ${labels.join(", ")}.`);
      }
    }
  }

  const tables = config.tables || [];
  if (tables.length === 0) {
    errors.push("Add at least one source table.");
  } else {
    tables.forEach((t, i) => {
      const row = i + 1;
      if (!String(t.name || "").trim()) errors.push(`Table ${row}: table name is required.`);
      if (!String(t.primary_key || "").trim()) errors.push(`Table ${row}: primary key column(s) is required.`);
      if (isFlat && !String(t.file || "").trim()) errors.push(`Table ${row}: select a source file.`);
      if (!isFlat && !String(t.schema || "").trim()) errors.push(`Table ${row}: schema/database name is required.`);
    });
  }

  if (
    String(config.step) === STEPS.STEP3 &&
    !String(config.profile_map_file || "").trim() &&
    Array.isArray(profileMaps) &&
    profileMaps.length === 0
  ) {
    errors.push(
      "No Profile Map is available to auto-generate from yet - run Step 1 first, or upload a Source-DQ-Profile-Map.xlsx, before running Step 3."
    );
  }

  return errors;
}
