export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:5050/api" : "/api");

export const JOB_POLL_INTERVAL = 1400;
export const MAX_PREVIEW_ROWS = 100;
export const JOBS_PAGE_SIZE = 10;
export const UPLOADS_PAGE_SIZE = 10;
export const CONNECTIONS_PAGE_SIZE = 10;
export const DEBOUNCE_DELAY = 300;

export const PAGE_CACHE_PREFIX = "dqc:v1";

export const PAGE_CACHE_TTL_MS = 5 * 60 * 1000;

export const PAGE_CACHE_MAX_ENTRIES = 40;

export const STORAGE_KEYS = {
  CURRENT_JOB_ID: "dq_current_job_id",
  CURRENT_JOB_META: "dq_current_job_meta",
  LATEST_RESULTS: "dq_latest_results",
  USER_CONFIG: "dq_user_config",
  RECENT_JOBS: "dq_recent_jobs",
};

export const DEFAULT_ROUTE = "/dashboards/dimensions";

export const PAGE_META = {
  "dashboards/dimensions": { title: "Dashboard", subtitle: "Data health across the five core quality dimensions." },
  "dashboards/data-sources": { title: "Data sources", subtitle: "Freshness, volume, distribution, schema and lineage per source." },
};

export const STEPS = {
  STEP1: "1",
  STEP3: "3",
};

export const UPLOAD_KINDS = [
  { value: "lov", label: "LOV Reference (CSV)", filterLabel: "LOV", accept: ".csv", multiple: true, sample: "lov" },
  { value: "profile_map", label: "Mapping File (Excel .xlsx)", filterLabel: "Mapping File", accept: ".xlsx", multiple: false, sample: null },
];

export const UPLOAD_KIND_LABELS = { lov: "LOV", profile_map: "Mapping" };
export const UPLOAD_KIND_PILLS = { lov: "pill-amber", profile_map: "pill-green" };

export const UPLOAD_ALLOWED_EXT = { lov: [".csv"], profile_map: [".xlsx"] };
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

export const STEP3_ONLY_SECTIONS = ["section-profile-map", "section-report-options"];
