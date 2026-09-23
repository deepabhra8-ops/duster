import { EMPTY_ROW } from "../components/profileMapper/SchemaTreePicker.jsx";

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
