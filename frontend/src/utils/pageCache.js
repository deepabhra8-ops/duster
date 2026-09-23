import {
  PAGE_CACHE_MAX_ENTRIES,
  PAGE_CACHE_PREFIX,
  PAGE_CACHE_TTL_MS,
} from "../constants/appConfig.js";

export const DENY_LIST = [
  "/reveal",
  "/test-connection",
  "/profile-map",
  "/schemas",
  "/tables",
  "/columns",
];

export function isCacheable(resource) {
  const value = String(resource || "");
  if (!value) return false;
  if (/^job:/.test(value)) return false;
  return !DENY_LIST.some((denied) => value.includes(denied));
}

function serializeParams(params) {
  if (!params) return "";
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`);
  return entries.join("&");
}

export function buildKey(scope, resource, params) {
  return `${PAGE_CACHE_PREFIX}:${scope || "anon"}:${resource}:${serializeParams(params)}`;
}

export function resourcePrefix(scope, resource) {
  return `${PAGE_CACHE_PREFIX}:${scope || "anon"}:${resource}:`;
}

const memory = new Map();
const listeners = new Set();

let hydrated = false;

function storage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

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
      }
    }
  } catch {
  }
}

function emit() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
    }
  });
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

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

function enforceCap(key) {
  const prefix = key.slice(0, key.lastIndexOf(":") + 1);

  const siblings = [...memory.entries()]
    .filter(([k]) => k.startsWith(prefix))
    .sort((a, b) => a[1].fetchedAt - b[1].fetchedAt);

  for (let i = 0; i <= siblings.length - PAGE_CACHE_MAX_ENTRIES; i += 1) {
    remove(siblings[i][0]);
  }
}

export function writeEntry(key, data) {
  hydrate();

  const entry = { data, fetchedAt: Date.now() };
  memory.set(key, entry);

  const store = storage();
  if (store) {
    try {
      store.setItem(key, JSON.stringify(entry));
    } catch {
    }
  }

  enforceCap(key);
  emit();
}

export function remove(key) {
  memory.delete(key);

  const store = storage();
  if (store) {
    try {
      store.removeItem(key);
    } catch {
    }
  }
}

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

export function clearAll() {
  hydrate();

  for (const key of [...memory.keys()]) remove(key);

  const store = storage();
  if (store) {
    try {
      for (let i = store.length - 1; i >= 0; i -= 1) {
        const key = store.key(i);
        if (key && key.startsWith(PAGE_CACHE_PREFIX)) store.removeItem(key);
      }
    } catch {
    }
  }

  emit();
}

export function __reset() {
  memory.clear();
  hydrated = false;
}
