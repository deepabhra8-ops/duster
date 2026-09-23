/**
 * useCachedResource.js - stale-while-revalidate for page-level list data.
 *
 * A cache hit paints immediately with `loading: false` (no skeleton flash) and
 * then revalidates in the background with `refreshing: true`. A miss behaves
 * exactly like the fetch it replaces, so every page's existing skeleton still
 * shows on a genuinely first visit.
 *
 * Two guards are carried over from the patterns already in this codebase rather
 * than invented here:
 *   - in-flight dedupe via a module-level Map, so two components mounting on the
 *     same key cost one request (useCatalog does this per instance with a Set);
 *   - a monotonic request id that discards a response which is no longer the
 *     newest, so a slow page-1 answer cannot overwrite the page-2 the user has
 *     already moved to (lifted from useJobList's requestIdRef).
 *
 * `refresh()` is what the toolbar button calls: it always goes to the network
 * and sets `refreshing`. `revalidate({ silent: true })` is for background work
 * such as useJobList's 1400 ms poll - it refreshes the cache without spinning
 * the icon, because spinning it every 1.4s while a job runs is noise.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { isCacheable, readEntry, writeEntry } from "../utils/pageCache.js";

// key -> Promise, so concurrent callers share one request.
const inFlight = new Map();

function dedupe(key, fetcher) {
  if (inFlight.has(key)) return inFlight.get(key);

  const promise = Promise.resolve()
    .then(fetcher)
    .finally(() => inFlight.delete(key));

  inFlight.set(key, promise);
  return promise;
}

/**
 * @param {object}   options
 * @param {string}   options.key       full cache key (see utils/pageCache.js)
 * @param {Function} options.fetcher   () => Promise<{ok, data, error}>
 * @param {Function} options.select    maps a successful `data` to what is stored
 * @param {boolean}  options.enabled   skip entirely when false
 */
export function useCachedResource({ key, fetcher, select, enabled = true }) {
  const cacheable = enabled && Boolean(key) && isCacheable(key);
  const cached = cacheable ? readEntry(key) : null;

  const [state, setState] = useState(() => ({
    data: cached?.data ?? null,
    error: null,
    // A cache hit must not render a skeleton - that is the whole point.
    loading: !cached,
    refreshing: false,
    lastUpdated: cached?.fetchedAt ?? null,
  }));

  const requestIdRef = useRef(0);
  const mounted = useRef(true);

  // Held in a ref so the effect below does not re-run every render just because
  // the caller passed a fresh closure.
  const fetcherRef = useRef(fetcher);
  const selectRef = useRef(select);
  fetcherRef.current = fetcher;
  selectRef.current = select;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async ({ silent = false, fromCache = false } = {}) => {
      if (!enabled || !key) return;

      const requestId = ++requestIdRef.current;

      setState((s) => ({
        ...s,
        // `fromCache` means we already have something on screen, so this is a
        // revalidation, not a load.
        loading: fromCache || silent ? s.loading : true,
        refreshing: silent ? s.refreshing : fromCache || s.data !== null,
        error: silent ? s.error : null,
      }));

      const result = await dedupe(key, () => fetcherRef.current());

      // A newer request has been issued; its answer is the current one.
      if (requestId !== requestIdRef.current) return;
      if (!mounted.current) return;

      if (!result?.ok) {
        setState((s) => ({
          ...s,
          loading: false,
          refreshing: false,
          // A failed background revalidation keeps the data already on screen
          // rather than blanking a page that was working a moment ago.
          error: result?.error || "Request failed",
        }));
        return;
      }

      const value = selectRef.current ? selectRef.current(result.data) : result.data;

      if (cacheable) writeEntry(key, value);

      setState({
        data: value,
        error: null,
        loading: false,
        refreshing: false,
        lastUpdated: Date.now(),
      });
    },
    [key, enabled, cacheable]
  );

  // On key change: serve the cache if there is one, then revalidate.
  useEffect(() => {
    if (!enabled || !key) return;

    const entry = cacheable ? readEntry(key) : null;

    if (entry) {
      setState({
        data: entry.data,
        error: null,
        loading: false,
        refreshing: true,
        lastUpdated: entry.fetchedAt,
      });
      run({ fromCache: true });
    } else {
      setState((s) => ({ ...s, data: null, loading: true, error: null }));
      run();
    }
    // `run` is stable for a given key; re-running on its identity is the intent.
  }, [key, enabled, cacheable, run]);

  /** Toolbar refresh: always hits the network, always shows the spinner. */
  const refresh = useCallback(() => run({ fromCache: true }), [run]);

  /** Background revalidation (polling): updates the cache, no spinner. */
  const revalidate = useCallback(() => run({ silent: true }), [run]);

  /**
   * Write through after an optimistic mutation, so the cache cannot drift from
   * what the user is looking at. Connections needs this: its create/edit/delete
   * update local state and never refetch.
   */
  const setData = useCallback(
    (updater) => {
      setState((s) => {
        const next = typeof updater === "function" ? updater(s.data) : updater;
        if (cacheable) writeEntry(key, next);
        return { ...s, data: next, lastUpdated: Date.now() };
      });
    },
    [key, cacheable]
  );

  return { ...state, refresh, revalidate, setData };
}

export default useCachedResource;
