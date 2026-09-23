/**
 * profileMapperRows.js - schema/table/column row <-> backend `tables` array
 * conversions shared by ProfileMapperJob.jsx's row picker and
 * NewProfileMapperJobModal.jsx's Database step 2 (both render
 * SchemaTreePicker.jsx-shaped rows). Factored out of ProfileMapperJob.jsx
 * so the new-job modal doesn't reimplement the same grouping logic.
 */
import { EMPTY_ROW } from "../components/profileMapper/SchemaTreePicker.jsx";

/** Real tables (schema/name/primary_key) → UI rows, all locked (only locked rows are ever persisted). */
export function tablesToRows(tables) {
  if (!tables || tables.length === 0) return [{ ...EMPTY_ROW }];
  const rows = [];
  for (const t of tables) {
    const cols = String(t.primary_key || "")
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);
    if (cols.length === 0) {
      rows.push({ schema: t.schema || "", table: t.name || "", column: "", locked: true });
    } else {
      cols.forEach((c) => rows.push({ schema: t.schema || "", table: t.name || "", column: c, locked: true }));
    }
  }
  return rows;
}

/** Locked UI rows → real tables - grouped by schema+table, Column values become that table's primary_key. */
export function rowsToTables(rows) {
  const grouped = new Map();
  for (const row of rows) {
    if (!row.locked || !row.schema || !row.table) continue;
    const key = `${row.schema}::${row.table}`;
    if (!grouped.has(key)) grouped.set(key, { schema: row.schema, name: row.table, columns: [] });
    if (row.column && !grouped.get(key).columns.includes(row.column)) {
      grouped.get(key).columns.push(row.column);
    }
  }
  return Array.from(grouped.values()).map((t) => ({
    schema: t.schema,
    name: t.name,
    primary_key: t.columns.join(", "),
  }));
}
