import axios from "axios";
import { API_BASE_URL } from "../constants/appConfig.js";

const DEFAULT_TIMEOUT = 30_000;
export const TRANSFER_TIMEOUT = 300_000;

export const http = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: DEFAULT_TIMEOUT,
  withCredentials: true,
});

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

async function request(promise) {
  try {
    const res = await promise;
    return { ok: true, data: res.data };
  } catch (err) {
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

export const healthCheck = () => get("/health");

export const login = (username, password) => post("/auth/login", { username, password });
export const logout = () => post("/auth/logout");
export const me = () => get("/auth/me");

export const testConnection = (databaseType, connectionDetails, chunkSize = 50000) =>
  post("/test-connection", { databaseType, connectionDetails, chunkSize });

export const testConnectionString = (connectionString) =>
  post("/test-connection", { connection_string: connectionString });

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

export const createConnection = (name, databaseType, connectionDetails, description = "") =>
  post("/connections", { name, databaseType, connectionDetails, description });

export const updateConnection = (id, name, databaseType, connectionDetails, description = "") =>
  patch(`/connections/${id}`, { name, databaseType, connectionDetails, description });

export const deleteConnection = (id) => del(`/connections/${id}`);

export const revealConnection = (id) => get(`/connections/${id}/reveal`);

export const heartbeatConnection = (id) => post(`/connections/${id}/heartbeat`);

export const getIngestionConfig = (id) => get(`/connections/${id}/ingestion`);

export const saveIngestionConfig = (id, latencyRequirement, schedulingOwnership) =>
  patch(`/connections/${id}/ingestion`, {
    latencyRequirement,
    schedulingOwnership,
  });

export const listConnectionSchemas = (id) => get(`/connections/${id}/schemas`);

export const refreshConnectionSchemas = (id) =>
  post(`/connections/${id}/schemas/refresh`);

export const listConnectionTables = (id, schema) =>
  get(`/connections/${id}/tables`, { params: { schema } });

export const listConnectionColumns = (id, schema, table) =>
  get(`/connections/${id}/columns`, { params: { schema, table } });

export async function uploadFile(file, kind) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("kind", kind);
  return request(
    http.post("/upload", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: TRANSFER_TIMEOUT,
    })
  );
}

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

export function previewUpload(kind, filename) {
  return get("/uploads/preview", { params: { kind, filename } });
}

export const uploadDownloadUrl = (kind, filename) =>
  `${API_BASE_URL}/uploads/download?kind=${encodeURIComponent(kind)}&filename=${encodeURIComponent(filename)}`;

export const submitJob = (params) => post("/run", params);
export const fetchJob = (jobId) => get(`/job/${jobId}`);
export const cancelJob = (jobId) => post(`/job/${jobId}/cancel`);
export const deleteJob = (jobId) => del(`/job/${jobId}`);

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

export const createDraftJob = (name, description, connectionId, step = "1", profileMapFile = null, tables = null, lovFile = null) => {
  const payload = { name, description, connection_id: connectionId, step };
  if (profileMapFile) payload.profile_map_file = profileMapFile;
  if (tables) payload.tables = tables;
  if (lovFile) payload.lov_file = lovFile;
  return post("/jobs/draft", payload);
};
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

export const fetchProfileMap = (jobId) => get(`/job/${jobId}/profile-map`);

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

export const downloadUrl = (jobId, kind) =>
  kind === "staging"
    ? `${API_BASE_URL}/job/${jobId}/staging/download`
    : `${API_BASE_URL}/job/${jobId}/download/${kind}`;

export const sampleLovUrl = () => `${API_BASE_URL}/sample-lov`;

export const listLovs = () => get("/lovs");

export const getLov = (filename) => get(`/lovs/${encodeURIComponent(filename)}`);

export const deleteLov = (filename) => del(`/lovs/${encodeURIComponent(filename)}`);

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

export const fetchDashboardSummary = () => get("/dashboard/summary");

export const listQualityRuleTemplates = () => get("/quality-rules/templates");
export const listQualityRules = () => get("/quality-rules");
export const fetchQualityRule = (ruleId) => get(`/quality-rules/${encodeURIComponent(ruleId)}`);
export const createQualityRule = (rule) => post("/quality-rules", rule);
export const updateQualityRule = (ruleId, rule) =>
  request(http.put(`/quality-rules/${encodeURIComponent(ruleId)}`, rule));
export const setQualityRuleEnabled = (ruleId, enabled) =>
  patch(`/quality-rules/${encodeURIComponent(ruleId)}`, { enabled });
export const duplicateQualityRule = (ruleId) => post(`/quality-rules/${encodeURIComponent(ruleId)}/duplicate`);
export const deleteQualityRule = (ruleId) => del(`/quality-rules/${encodeURIComponent(ruleId)}`);

// Resolving a scope reads metadata from every matching connection, so a dry run
// over "everything" can outlast the default JSON timeout.
export const dryRunQualityRules = (body) => post("/quality-rules/dry-run", body, { timeout: TRANSFER_TIMEOUT });

export const startQualityRun = (body) => post("/quality-rules/runs", body);
export const listQualityRuns = ({ page = 1, pageSize = 20 } = {}) =>
  get("/quality-rules/runs", { params: { page, pageSize } });
export const fetchQualityRun = (runId = "latest") => get(`/quality-rules/runs/${encodeURIComponent(runId)}`);
export const fetchQualityRunResults = (runId = "latest", { status = "ALL", page = 1, pageSize = 50 } = {}) =>
  get(`/quality-rules/runs/${encodeURIComponent(runId)}/results`, { params: { status, page, pageSize } });
export const cancelQualityRun = (runId) => post(`/quality-rules/runs/${encodeURIComponent(runId)}/cancel`);
export const qualityRunResultsCsvUrl = (runId = "latest") =>
  `${API_BASE_URL}/quality-rules/runs/${encodeURIComponent(runId)}/results.csv`;

export const listNotifications = ({ limit = 20, before, unreadOnly = false } = {}) =>
  get("/notifications", {
    params: { limit, before: before || undefined, unread: unreadOnly || undefined },
  });

export const markNotificationRead = (id) => patch(`/notifications/${id}`, { status: "read" });

export const markAllNotificationsRead = () => post("/notifications/read-all");

export const clearAllNotifications = () => del("/notifications");

export const notificationStreamUrl = () => `${API_BASE_URL}/notifications/stream`;
