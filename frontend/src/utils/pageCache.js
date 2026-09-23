/**
 * pageCache.js - browser-side cache for page-level list data.
 *
 * Backed by sessionStorage with an in-memory mirror, so a read costs nothing per
 * render and the data still survives an F5. sessionStorage rather than
 * localStorage is deliberate: a tab close ends the cache, which keeps one user's
 * job names, connection names and dashboard figures off a shared machine.
 *
 * Keys are `dqc:v1:<scope>:<resource>:<params>`:
 *   - `v1` retires every entry at once when a response shape changes.
 *   - `<scope>` is the USERNAME for per-user data and "shared" for the
 *     connections list. This is load-bearing, not decoration: GET /jobs and
 *     GET /dashboard/summary are both filtered server-side by
 *     `Job.created_by == username`, so an unscoped key would show one user's
 *     jobs to the next person to log in on the same machine. GET /connections
 *     really is shared (list_all() has no owner filter).
 *   - `<params>` is serialized with sorted keys so {page,search} and
 *     {search,page} cannot produce two entries for one query.
 *
 * Every storage touch is wrapped in try/catch. sessionStorage throws in private
 * mode and when the quota is exceeded, and a cache must degrade to "no cache"
 * rather than break the page.
 *
 * NOT a general response cache. Results endpoints and anything carrying
 * credentials or a concurrency token are excluded by never being routed through
 * here - see DENY_LIST below for the reasoning.
 */
import {
  PAGE_CACHE_MAX_ENTRIES,
  PAGE_CACHE_PREFIX,
  PAGE_CACHE_TTL_MS,
} from "../constants/appConfig.js";

/**
 * Endpoints that must never be cached, and why. Kept as data so the rule is
 * testable rather than a convention someone has to remember:
 *
 *  - /job/{id}          ValidatorJob renders the whole validation report from
 *                       this one response (job.summary). There is no separate
 *                       results endpoint, so caching the job header would cache
 *                       the results with it.
 *  - /profile-map       Carries `version`, the optimistic-concurrency token
 *                       echoed back on save. A cached version produces spurious
 *                       409s and makes a valid edit look rejected.
 *  - /reveal            Decrypted connection credentials.
 *  - /test-connection   Plaintext credentials in the request body.
 *  - /schemas /tables /columns
 *                       Deliberately read live (migration 007). Caching them
 *                       would silently revert that.
 */
export const DENY_LIST = [
  "/reveal",
  "/test-connection",
  "/profile-map",
  "/schemas",
  "/tables",
  "/columns",
];

/** True if `resource` names something that must never be cached. */
export function isCacheable(resource) {
  const value = String(resource || "");
  if (!value) return false;
  if (/^job:/.test(value)) return false; // a single job carries its results
  return !DENY_LIST.some((denied) => value.includes(denied));
}

/* ── key building ─────────────────────────────────────────────── */

function serializeParams(params) {
  if (!params) return "";
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`);
  return entries.join("&");
}

/**
 * Build a cache key.
 * @param {string} scope     username, or "shared" for non-user-scoped data
 * @param {string} resource  e.g. "jobs", "connections", "dashboard"
 * @param {object} [params]  query inputs that change the response
 */
export function buildKey(scope, resource, params) {
  return `${PAGE_CACHE_PREFIX}:${scope || "anon"}:${resource}:${serializeParams(params)}`;
}

/** The prefix covering every entry of one resource, for invalidate(). */
export function resourcePrefix(scope, resource) {
  return `${PAGE_CACHE_PREFIX}:${scope || "anon"}:${resource}:`;
}

/* ── store ────────────────────────────────────────────────────── */

// Mirrors sessionStorage so reads during render never touch storage.
const memory = new Map();
const listeners = new Set();

let hydrated = false;

function storage() {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked entirely (some privacy modes)
  }
}

/** Load existing entries once per page load, so an F5 keeps the cache. */
function hydrate() {
  if (hydrated) return;
  hydrated = true;

  const store = storage();
  if (!store) return;

  try {
    for (let i = 0; i < store.length; i += 1) {
      const key = store.key(i);
      if (!key || !key.startsWith(PAGE_CACHE_PREFIX)) continue;
      try {
        memory.set(key, JSON.parse(store.getItem(key)));
      } catch {
        /* a malformed entry is simply skipped */
      }
    }
  } catch {
    /* iteration can throw if storage is revoked mid-session */
  }
}

function emit() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      /* a bad subscriber must not stop the others */
    }
  });
}

/** Subscribe to cache changes (backs useSyncExternalStore). */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Read an entry, or null when absent or past its TTL.
 * @returns {{data: *, fetchedAt: number} | null}
 */
export function readEntry(key) {
  hydrate();

  const entry = memory.get(key);
  if (!entry) return null;

  if (Date.now() - entry.fetchedAt > PAGE_CACHE_TTL_MS) {
    remove(key);
    return null;
  }

  return entry;
}

/** Evict oldest entries beyond the per-resource cap (deep paging guard). */
function enforceCap(key) {
  const prefix = key.slice(0, key.lastIndexOf(":") + 1);

  const siblings = [...memory.entries()]
    .filter(([k]) => k.startsWith(prefix))
    .sort((a, b) => a[1].fetchedAt - b[1].fetchedAt);

  for (let i = 0; i <= siblings.length - PAGE_CACHE_MAX_ENTRIES; i += 1) {
    remove(siblings[i][0]);
  }
}

/** Store a response against `key`, stamped with the current time. */
export function writeEntry(key, data) {
  hydrate();

  const entry = { data, fetchedAt: Date.now() };
  memory.set(key, entry);

  const store = storage();
  if (store) {
    try {
      store.setItem(key, JSON.stringify(entry));
    } catch {
      // Quota exceeded, or storage is read-only. The in-memory mirror still
      // serves this tab; persistence is the part we give up, not correctness.
    }
  }

  enforceCap(key);
  emit();
}

/** Drop one entry. */
export function remove(key) {
  memory.delete(key);

  const store = storage();
  if (store) {
    try {
      store.removeItem(key);
    } catch {
      /* ignore */
    }
  }
}

/**
 * Drop every entry under `prefix`.
 *
 * This is what makes paginated invalidation correct: deleting a job shifts every
 * later page of an offset-paginated list, so one mutation has to clear all of
 * them, not just the page currently on screen.
 */
export function invalidate(prefix) {
  hydrate();

  let changed = false;

  for (const key of [...memory.keys()]) {
    if (key.startsWith(prefix)) {
      remove(key);
      changed = true;
    }
  }

  if (changed) emit();
}

/**
 * Drop everything this module owns.
 *
 * Called on sign-out AND on a 401, because a session that expires server-side
 * never runs through logout() at all.
 */
export function clearAll() {
  hydrate();

  for (const key of [...memory.keys()]) remove(key);

  // Also sweep storage directly: another tab may have written entries this
  // tab's mirror never saw.
  const store = storage();
  if (store) {
    try {
      for (let i = store.length - 1; i >= 0; i -= 1) {
        const key = store.key(i);
        if (key && key.startsWith(PAGE_CACHE_PREFIX)) store.removeItem(key);
      }
    } catch {
      /* ignore */
    }
  }

  emit();
}

/** Test seam: forget the hydration flag and the mirror. */
export function __reset() {
  memory.clear();
  hydrated = false;
}
