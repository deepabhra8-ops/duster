import { listConnections } from "../api/api.js";

/**
 * Normalizes /api/connections. The backend's SavedConnection model carries no live
 * status, schema/table counts, or per-connection score today — those fields are left
 * undefined here so ConnectionCard renders its documented disconnected-state em-dashes
 * rather than fabricated data. See the Duster Frontend Rebuild plan, "Page composition".
 */
export async function listConnectionsSummary() {
  const { ok, data, error } = await listConnections();
  if (!ok) return { ok, error };

  const rows = data?.data || data || [];

  return {
    ok: true,
    data: rows.map((row) => ({
      id: row.id,
      name: row.name,
      dbType: row.db_type,
      description: row.description || "",
    })),
  };
}

export default { listConnectionsSummary };
