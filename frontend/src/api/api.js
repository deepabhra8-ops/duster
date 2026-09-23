/**
 * api.js - ALL backend communication lives here (Axios edition).
 *
 * Mirrors the original vanilla api.js surface and its return contract:
 *   success → { ok: true,  data }
 *   failure → { ok: false, error }
 * so page implementations can consume it the same way.
 *
 * Backend host: http://localhost:5050  (routes under /api)
 */
import axios from "axios";
import { API_BASE_URL } from "../constants/appConfig.js";


/* ── Timeouts ────────────────────────────────────────────────────
 * Axios defaults to no timeout at all, so a request that never answers - a
 * hung backend, a dropped connection a proxy keeps open - leaves its caller
 * awaiting forever. Every page that awaits one of these calls sits on
 * `loading: true` with no error and no way out but a manual refresh.
 *
 * The default is for ordinary JSON calls. Transfers that are legitimately slow
 * - a 200MB upload, a report workbook streamed out of S3 - pass TRANSFER_TIMEOUT
 * explicitly; a 30s cap on those would break them.
 */
const DEFAULT_TIMEOUT = 30_000;
export const TRANSFER_TIMEOUT = 300_000;

/* ── Axios instance ──────────────────────────────────────────── */
export const http = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: DEFAULT_TIMEOUT,
  // Send/receive the httpOnly session cookie set by POST /auth/login.
  withCredentials: true,
});

/**
 * Registered by AuthProvider so a session that has expired or been signed
 * out (any 401 from the API) is reflected app-wide immediately, not just on
 * whichever page happened to make the failing call.
 */
let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) unauthorizedHandler?.();
    return Promise.reject(err);
  }
);

/* ── Generic request wrapper ─────────────────────────────────── */
async function request(promise) {
  try {
    const res = await promise;
    return { ok: true, data: res.data };
  } catch (err) {
    // A timeout arrives with no response, so it would otherwise surface as
    // axios's own "timeout of 30000ms exceeded" - accurate but meaningless to
    // whoever is looking at the screen.
    if (err?.code === "ECONNABORTED") {
      return { ok: false, error: "The server took too long to respond. Please try again." };
    }

    const message =
      err?.response?.data?.error ||
      (err?.response ? `HTTP ${err.response.status}` : err.message) ||
      "Request failed";
    return { ok: false, error: message };
  }
}

const get = (path, config) => request(http.get(path, config));
const post = (path, body, config) => request(http.post(path, body, config));
const patch = (path, body, config) => request(http.patch(path, body, config));
const del = (path, config) => request(http.delete(path, config));

/* ── Health ──────────────────────────────────────────────────── */
export const healthCheck = () => get("/health");

/* ── Auth ────────────────────────────────────────────────────── */
export const login = (username, password) => post("/auth/login", { username, password });
export const logout = () => post("/auth/logout");
export const me = () => get("/auth/me");

/* ── Connection test (new multi-db format) ───────────────────── */
export const testConnection = (databaseType, connectionDetails, chunkSize = 50000) =>
  post("/test-connection", { databaseType, connectionDetails, chunkSize });

/* ── Legacy connection string test ───────────────────────────── */
export const testConnectionString = (connectionString) =>
  post("/test-connection", { connection_string: connectionString });

/* ── Saved connections (Connections manager) ─────────────────── */
/**
 * listConnections - two callers, two shapes.
 *
 * Called with no `opts` (the job wizard's connection picker, useSavedConnections.js):
 * every saved connection's non-secret fields, unpaginated - the picker needs
 * the whole list to search/select from, not just the first page.
 *
 * Called with `opts` (the Connections manager page): server-side paginated,
 * searched and sorted, same {page, pageSize, search, dbType, sortOrder} shape
 * as listJobs/listUploads. Sending zero query params is what tells the
 * backend apart from the paginated call - see GET /api/connections.
 */
export function listConnections(opts) {
  if (!opts) return get("/connections");

  return get("/connections", {
    params: {
      page: opts.page || 1,
      pageSize: opts.pageSize || 10,
      search: opts.search || "",
      dbType: opts.dbType || "",
      sortOrder: opts.sortOrder || "desc",
    },
  });
}

/** Save a new database connection. `port` isn't a param - the backend derives it from connectionDetails.port when present. */
export const createConnection = (name, databaseType, connectionDetails, description = "") =>
  post("/connections", { name, databaseType, connectionDetails, description });

/** Update an existing saved connection's fields - same shape as createConnection. */
export const updateConnection = (id, name, databaseType, connectionDetails, description = "") =>
  patch(`/connections/${id}`, { name, databaseType, connectionDetails, description });

/** Delete a saved connection. */
export const deleteConnection = (id) => del(`/connections/${id}`);

/**
 * Reveal a saved connection's decrypted details - used only by the Jobs
 * "New Job" wizard right after picking a saved connection (to drive live
 * schema/table browsing, same as typing credentials in fresh). Never
 * persisted client-side.
 */
export const revealConnection = (id) => get(`/connections/${id}/reveal`);

/* ── Catalog, one level at a time ─────────────────────────────
 *
 * The catalog is never fetched as a whole. Saving a connection stores only its
 * schema names (small, and what makes the first dropdown instant); a schema's
 * tables and a table's columns are fetched when the user actually opens them,
 * so cost scales with what they look at rather than with the size of the
 * database.
 */

/** Stored schema names for a connection - no database round trip. `{ schemas: [...] }`. */
export const listConnectionSchemas = (id) => get(`/connections/${id}/schemas`);

/** Re-query and store the connection's schema names. `{ schemas: [...] }`. */
export const refreshConnectionSchemas = (id) =>
  post(`/connections/${id}/schemas/refresh`);

/** Tables in one schema, fetched live. `{ tables: [...] }`. */
export const listConnectionTables = (id, schema) =>
  get(`/connections/${id}/tables`, { params: { schema } });

/** Columns in one table, fetched live. `{ columns: [...] }`. */
export const listConnectionColumns = (id, schema, table) =>
  get(`/connections/${id}/columns`, { params: { schema, table } });

/* ── File uploads ────────────────────────────────────────────── */
export async function uploadFile(file, kind) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("kind", kind);
  // Override the default JSON content-type so the browser sets the
  // multipart boundary itself.
  return request(
    http.post("/upload", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      // Uploads run to MAX_UPLOAD_SIZE_BYTES (200MB); the default 30s cap would
      // abort a large one part-way.
      timeout: TRANSFER_TIMEOUT,
    })
  );
}

/**
 * listUploads - supports pagination, search, sort, filter.
 * @param {object} opts - { page, pageSize, search, fileType, sortBy, sortOrder }
 */
export function listUploads(opts = {}) {
  return get("/uploads", {
    params: {
      page: opts.page || 1,
      pageSize: opts.pageSize || 10,
      search: opts.search || "",
      fileType: opts.fileType || "",
      sortBy: opts.sortBy || "created_at",
      sortOrder: opts.sortOrder || "desc",
    },
  });
}

/** Preview an uploaded file (first N rows). */
export function previewUpload(kind, filename) {
  return get("/uploads/preview", { params: { kind, filename } });
}

/** Download URL for an uploaded file. */
export const uploadDownloadUrl = (kind, filename) =>
  `${API_BASE_URL}/uploads/download?kind=${encodeURIComponent(kind)}&filename=${encodeURIComponent(filename)}`;

/* ── Jobs / pipeline ─────────────────────────────────────────── */
export const submitJob = (params) => post("/run", params);
export const fetchJob = (jobId) => get(`/job/${jobId}`);
export const cancelJob = (jobId) => post(`/job/${jobId}/cancel`);
export const deleteJob = (jobId) => del(`/job/${jobId}`);

/**
 * listJobs - supports pagination, search, sort, and optional `step`
 * ("1" = Profile Mapper, "3" = DQ Validator - omit for the generic Jobs
 * page, which shows every step), `status`, and `dbType` filters, all
 * server-side.
 * @param {object} opts - { page, pageSize, search, sortBy, sortOrder, step, status, dbType }
 */
export function listJobs(opts = {}) {
  return get("/jobs", {
    params: {
      page: opts.page || 1,
      pageSize: opts.pageSize || 10,
      search: opts.search || "",
      sortBy: opts.sortBy || "started",
      sortOrder: opts.sortOrder || "desc",
      step: opts.step || undefined,
      status: opts.status || undefined,
      dbType: opts.dbType || undefined,
    },
  });
}

/**
 * Draft job lifecycle (Profile Mapper's create-then-configure-then-start
 * flow - see docs/ux-plan.md §5): create a draft (not running yet), add its
 * tables as rows get locked, then start it for real.
 */
export const createDraftJob = (name, description, connectionId, step = "1", sourceType = "database", profileMapFile = null, tables = null, lovFile = null) => {
  const payload = { name, description, connection_id: connectionId, step, source_type: sourceType };
  if (profileMapFile) payload.profile_map_file = profileMapFile;
  if (tables) payload.tables = tables;
  // At most one LOV per job - the job validates against this file alone.
  if (lovFile) payload.lov_file = lovFile;
  return post("/jobs/draft", payload);
};
/**
 * DQ Validator's own draft creation (Validator.jsx's "New Job" flow) - not a
 * variant of createDraftJob above: instead of a source_type/connection_id the
 * caller picks directly, this names a completed Profile Mapper job
 * (source_job_id) and the backend copies its source config + materializes
 * its profile-map findings server-side (JobService.create_validator_job_from_profile_map).
 */
export const createValidatorJobFromProfileMap = (name, description, sourceJobId, lovFile = null) =>
  post("/jobs/validator-draft", {
    name,
    description,
    source_job_id: sourceJobId,
    ...(lovFile ? { lov_file: lovFile } : {}),
  });
export const updateJobTables = (jobId, tables) => patch(`/job/${jobId}/tables`, { tables });
export const updateJobDetails = (jobId, name, description) =>
  patch(`/job/${jobId}/details`, { name, description });
export const startJob = (jobId) => post(`/job/${jobId}/start`);

/**
 * A finished Profile Mapper job's generated profile map, parsed into JSON
 * rows (ProfileMapWriter.COLUMNS shape) via the engine's own ProfileMapReader
 * (ProfileMapResultService) - backs ProfileMapperJob.jsx's Profile Map
 * Results table. 404s (returned as `ok: false`) until the job is done.
 */
export const fetchProfileMap = (jobId) => get(`/job/${jobId}/profile-map`);

/**
 * Apply a batch of Profile Map cell edits and/or added rule rows - backs
 * ProfileMapperJob.jsx's Edit/Save flow. Both land in one server-side transaction.
 *
 * `edits`: [{row_id, changes: {<editable column name>: <new value>}}, ...] - row_id is
 * always one the server issued; this client never mints one.
 * `additions`: [{source_row_id, changes: {Applicable Rules, Rule Parameters, Analyst Notes}}]
 * - a new rule row for the column that `source_row_id` belongs to. The server clones that
 * row's profiling metadata and assigns the new row's id, returning it in `rows`.
 * `removals`: [row_id] - rule rows to drop. The server keeps a column's last rule.
 * `version`: the version this client last loaded (fetchProfileMap's own `version` field, or a
 * prior updateProfileMapCells call's).
 *
 * Doesn't go through the shared request() helper above: a 409 (stale version - someone else
 * saved an edit since this client last loaded it) carries the server's current rows/version in
 * its body, which the caller needs to refresh its baseline against - request() would discard
 * everything but the error string. `conflict: true` is how a caller tells that apart from any
 * other failure (validation, network, job not found).
 */
export async function updateProfileMapCells(jobId, version, edits, additions = [], removals = []) {
  try {
    const res = await http.patch(`/job/${jobId}/profile-map`, {
      version,
      edits,
      additions,
      removals,
    });
    return { ok: true, rows: res.data.rows, version: res.data.version };
  } catch (err) {
    const body = err?.response?.data;
    const message =
      body?.error || (err?.response ? `HTTP ${err.response.status}` : err.message) || "Request failed";

    if (err?.response?.status === 409 && body) {
      return { ok: false, conflict: true, error: message, rows: body.rows, version: body.version };
    }
    return { ok: false, conflict: false, error: message };
  }
}

/**
 * Upload and inspect a profile map workbook without creating a job.
 */
export async function inspectProfileMapWorkbook(file) {
  const fd = new FormData();
  fd.append("file", file);
  return request(
    http.post("/profile-map/inspect", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: TRANSFER_TIMEOUT,
    })
  );
}

/** Build a download URL (opens in a new tab). */
export const downloadUrl = (jobId, kind) =>
  kind === "staging"
    ? `${API_BASE_URL}/job/${jobId}/staging/download`
    : `${API_BASE_URL}/job/${jobId}/download/${kind}`;

/** Sample CSV download URL. */
export const sampleCsvUrl = () => `${API_BASE_URL}/sample-csv`;

/** Sample LOV CSV download URL. */
export const sampleLovUrl = () => `${API_BASE_URL}/sample-lov`;

/** List all available LOV files with names, filenames, and value counts. */
export const listLovs = () => get("/lovs");

/** Read one LOV file's entry (display name + the LOV names inside it). */
export const getLov = (filename) => get(`/lovs/${encodeURIComponent(filename)}`);

/** Delete a single LOV file by its on-disk filename. */
export const deleteLov = (filename) => del(`/lovs/${encodeURIComponent(filename)}`);


/* ── Database metadata discovery ─────────────────────────────── */
export const listDatabaseMetadata = (
  databaseType,
  connectionDetails,
  params = {}
) =>
  post("/metadata", {
    databaseType,
    connectionDetails,
    level: params.level || "schemas",
    schema: params.schema || "",
    table: params.table || "",
    search: params.search || "",
  });

/* ── Dashboard ───────────────────────────────────────────────── */
/** Aggregate stats for the Home dashboard (job counts, recent activity, score trend). */
export const fetchDashboardSummary = () => get("/dashboard/summary");

/* ── Notifications (the top bar's bell) ──────────────────────── */
/**
 * One page of the signed-in user's notifications, newest first.
 * Resolves to `{ ok, data: { ok, data: { items, unread_count, next_cursor } } }` - `unread_count`
 * is the user's total, not the page's. Pass the previous page's `next_cursor` as `before` to
 * continue; it is null on the last page. Keyset-paged, so a notification arriving mid-scroll
 * cannot shift a page.
 */
export const listNotifications = ({ limit = 20, before, unreadOnly = false } = {}) =>
  get("/notifications", {
    params: { limit, before: before || undefined, unread: unreadOnly || undefined },
  });

/** Mark one notification read. Resolves with the notification and the user's new `unread_count`. */
export const markNotificationRead = (id) => patch(`/notifications/${id}`, { status: "read" });

/** Mark every notification read. Resolves with `{ updated, unread_count }`. */
export const markAllNotificationsRead = () => post("/notifications/read-all");

/** Permanently delete every one of the user's notifications, read and unread. Resolves with `{ deleted, unread_count }`. */
export const clearAllNotifications = () => del("/notifications");

/**
 * URL of the live notification stream (Server-Sent Events) - consumed by an EventSource, not
 * axios. Authenticated by the session cookie, so the caller must pass `withCredentials: true`.
 */
export const notificationStreamUrl = () => `${API_BASE_URL}/notifications/stream`;
