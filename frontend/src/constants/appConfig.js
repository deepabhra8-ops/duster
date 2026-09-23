import { SOURCE_TYPES } from "./sourceTypes.js";

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

export const DEFAULT_ROUTE = "/home";

import { createElement } from "react";
import { LayoutDashboard, Library, Database } from "lucide-react";
import { IconSettings, IconMap, IconActivity } from "../components/Icons.jsx";

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

export const UPLOAD_KINDS = [
  { value: "data", label: "Flat File Source (CSV)", filterLabel: "Flat File Source", accept: ".csv,.xlsx", multiple: true, sample: "csv" },
  { value: "lov", label: "LOV Reference (CSV)", filterLabel: "LOV", accept: ".csv", multiple: true, sample: "lov" },
  { value: "profile_map", label: "Mapping File (Excel .xlsx)", filterLabel: "Mapping File", accept: ".xlsx", multiple: false, sample: null },
];

export const UPLOAD_KIND_LABELS = { data: "Flat File", lov: "LOV", profile_map: "Mapping" };
export const UPLOAD_KIND_PILLS = { data: "pill-blue", lov: "pill-amber", profile_map: "pill-green" };

export const UPLOAD_ALLOWED_EXT = { data: [".csv", ".xlsx"], lov: [".csv"], profile_map: [".xlsx"] };
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

export const STEP3_ONLY_SECTIONS = ["section-profile-map", "section-report-options"];

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
