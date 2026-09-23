/**
 * appConfig.js - App-level constants ported from the original config.js
 * (everything that is not source-type, db-field, or DQ-rule specific).
 */
import { SOURCE_TYPES } from "./sourceTypes.js";

/**
 * Base URL for the FastAPI backend API. Routes are served under /api.
 * Configurable via Vite env var VITE_API_BASE_URL (see .env).
 * Backend host: http://localhost:5050
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:5050/api" : "/api");

export const JOB_POLL_INTERVAL = 1400; // ms
export const MAX_PREVIEW_ROWS = 100;
export const JOBS_PAGE_SIZE = 10;
export const UPLOADS_PAGE_SIZE = 10;
export const CONNECTIONS_PAGE_SIZE = 10;
export const DEBOUNCE_DELAY = 300; // ms for search debounce

/* ── Page cache (utils/pageCache.js) ──────────────────────────────
 * Browser-side cache for page-level list data, so returning to a page paints
 * from sessionStorage instead of a skeleton. sessionStorage, not localStorage:
 * it survives an F5 but dies with the tab, which keeps one user's job and
 * connection names off a shared machine once the tab is closed.
 */

/** Namespace + schema version for every cache key. Bump v1 when a cached
 *  response shape changes, so new code never reads an old object. */
export const PAGE_CACHE_PREFIX = "dqc:v1";

/** Beyond this age an entry is treated as a miss and the skeleton shows again,
 *  so genuinely old data is never presented as current. */
export const PAGE_CACHE_TTL_MS = 5 * 60 * 1000;

/** Per-resource LRU cap. Paging deeply would otherwise accumulate one entry per
 *  page for the life of the tab. */
export const PAGE_CACHE_MAX_ENTRIES = 40;

/** localStorage keys (kept identical to the vanilla app for continuity). */
export const STORAGE_KEYS = {
  CURRENT_JOB_ID: "dq_current_job_id",
  CURRENT_JOB_META: "dq_current_job_meta",
  LATEST_RESULTS: "dq_latest_results",
  USER_CONFIG: "dq_user_config",
  RECENT_JOBS: "dq_recent_jobs",
};

/** Default route - where "/" redirects to. */
export const DEFAULT_ROUTE = "/home";

/**
 * Sidebar navigation model: grouped sections of nav items.
 * Each item: { id (page id), label, icon }. `icon` is either an image path
 * (served from public/icons/) or an emoji fallback for items that don't
 * have an image yet.
 *
 * Groups still exist (for spacing/grouping in the markup) but none render a
 * section-label header - `section` is kept empty on every group rather than
 * removed, so a label can be reintroduced later without restructuring this.
 *
 * An item with an `accordion` (Discovery, below) is not a route link at all -
 * Sidebar.jsx renders it as a toggle that opens inline, in the rail itself,
 * rather than going anywhere on its own. `accordion` is a list of catalog
 * sections, each `{ id, label, icon, items: [{ to, label, end? }] }` - the
 * same shape the old second-tier SubNav panel used for Rule Reference /
 * Data Catalog, now nested under one rail item instead of living beside it.
 */
import { createElement } from "react";
import { LayoutDashboard, Library, Database } from "lucide-react";
import { IconSettings, IconMap, IconActivity } from "../components/Icons.jsx";

/* Sized to 20px to match .sb-item-icon's fixed box - the other nav icons are
   hand-drawn at width/height "1em", which resolves to the same 20px via
   .sb-item-icon-react's font-size, but lucide-react icons default to a fixed
   24px unless told otherwise, so this one needs it explicit. Plain
   createElement rather than JSX: this file is .js, outside the JSX-enabled
   .jsx set esbuild transforms. */
const IconDashboard = (props) => createElement(LayoutDashboard, { size: 20, ...props });

export const NAV_SECTIONS = [
  {
    section: "",
    items: [{ id: "home", label: "Dashboard", icon: IconDashboard }],
  },
  {
    section: "",
    items: [
      { id: "profile-mapper", label: "Profile Mapper", icon: IconMap },
      { id: "validator", label: "Validator", icon: IconActivity },
    ],
  },
  {
    section: "",
    items: [
      {
        id: "discovery",
        label: "Discovery",
        icon: IconSettings,
        accordion: [
          {
            id: "rule-catalog",
            label: "Rule Catalog",
            icon: Library,
            items: [
              { to: "/rules/catalog/dimension", label: "Dimension" },
              { to: "/rules/catalog/rules", label: "Rules" },
              { to: "/rules", label: "References", end: true },
            ],
          },
          {
            id: "data-catalog",
            label: "Data Catalog",
            icon: Database,
            items: [
              { to: "/data-catalog/assets", label: "Data Assets" },
              { to: "/configure", label: "Connections" },
              { to: "/data-catalog/glossary", label: "Glossary" },
            ],
          },
        ],
      },
    ],
  },
];

/** Page header copy keyed by page id (title + subtitle). */
export const PAGE_META = {
  home: { title: "DQ Job Summary", subtitle: "Overview and recent activity." },
  configure: { title: "Connections", subtitle: "Saved database connections for your pipelines." },
  "profile-mapper": { title: "Profile Mapper", subtitle: "Review and edit the profile map generated for your source data." },
  validator: { title: "Validator", subtitle: "Review DQ Validator results for your pipeline runs." },
  jobs: { title: "Job History", subtitle: "All pipeline runs this session. Click Log to re-view, Report to download." },
  rules: { title: "DQ Rule Reference", subtitle: "All 11 rule categories, dimensions, and parameter syntax." },
  "data-catalog": { title: "Data Catalog", subtitle: "Data assets, connections, and glossary." },
};

export const STEPS = {
  STEP1: "1",
  STEP3: "3",
};

/**
 * Upload file kinds. Each: { value, label (upload select), filterLabel,
 * accept (input accept attr), multiple, sample ("csv" | "lov" | null) }
 */
export const UPLOAD_KINDS = [
  { value: "data", label: "Flat File Source (CSV)", filterLabel: "Flat File Source", accept: ".csv,.xlsx", multiple: true, sample: "csv" },
  { value: "lov", label: "LOV Reference (CSV)", filterLabel: "LOV", accept: ".csv", multiple: true, sample: "lov" },
  { value: "profile_map", label: "Mapping File (Excel .xlsx)", filterLabel: "Mapping File", accept: ".xlsx", multiple: false, sample: null },
];

/** Display label + pill class per upload kind (for the files table). */
export const UPLOAD_KIND_LABELS = { data: "Flat File", lov: "LOV", profile_map: "Mapping" };
export const UPLOAD_KIND_PILLS = { data: "pill-blue", lov: "pill-amber", profile_map: "pill-green" };

/** Allowed extensions per kind (validation) and the hard size cap. */
export const UPLOAD_ALLOWED_EXT = { data: [".csv", ".xlsx"], lov: [".csv"], profile_map: [".xlsx"] };
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024; // 200 MB

/** Sections hidden when Step 1 is selected (Configure page). */
export const STEP3_ONLY_SECTIONS = ["section-profile-map", "section-report-options"];

/** Default pipeline configuration. */
export const DEFAULT_CONFIG = {
  project_name: "SMART_DataHub",
  run_mode: 1,
  step: "1",
  source_type: SOURCE_TYPES.FLAT_FILE,
  databaseType: "",
  connectionDetails: {},
  connection_string: "",
  chunk_size: 50000,
  include_failed_rows: true,
  profile_map_file: "",
  tables: [],
  lov_tables: {},
};
