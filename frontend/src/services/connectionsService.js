import { listConnections } from "../api/api.js";

const CATEGORY_BY_DB_TYPE = {
  snowflake: "Warehouses & lakehouses",
  bigquery: "Warehouses & lakehouses",
  redshift: "Warehouses & lakehouses",
  databricks: "Warehouses & lakehouses",
  postgresql: "Databases",
  mysql: "Databases",
  mssql: "Databases",
  oracle: "Databases",
  azure_sql: "Databases",
  salesforce: "SaaS & data catalogs",
};

const STATUS_META = {
  healthy: { tone: "success", label: "Connected" },
  warning: { tone: "warning", label: "Degraded" },
  error: { tone: "danger", label: "Disconnected" },
  unknown: { tone: "idle", label: "Not yet tested" },
};

function variantFor(status) {
  return status === "error" || status === "warning" ? status : "connected";
}

/** Backend timestamps are naive UTC (see backend/services/connection_health_service.py) and
 * serialize without a timezone suffix — treat them as UTC rather than letting the browser
 * assume local time. */
function parseUtc(value) {
  if (!value) return null;
  const iso = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function timeAgo(value) {
  const date = parseUtc(value);
  if (!date) return null;

  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "synced just now";

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `synced ${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `synced ${hours}h ago`;

  const days = Math.round(hours / 24);
  return `synced ${days}d ago`;
}

/**
 * Normalizes /api/connections. The backend's SavedConnection model now tracks per-connection
 * health (last_test_status/last_tested_at/schema_count/table_count) via the connection
 * heartbeat sweep (see backend/services/connection_health_service.py) — this maps those
 * fields into the shape ConnectionCard expects. `avgScore` is intentionally left out: it
 * belongs to the data-quality scoring feature, not connection health, so ConnectionCard
 * renders its documented em-dash for that stat.
 */
export async function listConnectionsSummary() {
  const { ok, data, error } = await listConnections();
  if (!ok) return { ok, error };

  const rows = data?.data || data || [];

  return {
    ok: true,
    data: rows.map((row) => {
      const status = row.last_test_status || "unknown";
      const meta = STATUS_META[status] || STATUS_META.unknown;

      return {
        id: row.id,
        name: row.name,
        dbType: row.db_type,
        description: row.description || "",
        category: CATEGORY_BY_DB_TYPE[row.db_type] || "Databases",
        variant: variantFor(status),
        statusTone: meta.tone,
        statusLabel: meta.label,
        statusDetail: timeAgo(row.last_tested_at),
        stats: {
          schemas: row.schema_count ?? undefined,
          tables: row.table_count ?? undefined,
        },
        errorNote:
          status === "error"
            ? row.last_test_error ||
              "Duster could not reach this connection. Verify credentials and network access, then retry."
            : undefined,
      };
    }),
  };
}

export default { listConnectionsSummary };
