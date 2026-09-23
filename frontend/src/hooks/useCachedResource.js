import { useCallback, useEffect, useRef, useState } from "react";

import { isCacheable, readEntry, writeEntry } from "../utils/pageCache.js";

const inFlight = new Map();

function dedupe(key, fetcher) {
  if (inFlight.has(key)) return inFlight.get(key);

  const promise = Promise.resolve()
    .then(fetcher)
    .finally(() => inFlight.delete(key));

  inFlight.set(key, promise);
  return promise;
}

export function useCachedResource({ key, fetcher, select, enabled = true }) {
  const cacheable = enabled && Boolean(key) && isCacheable(key);
  const cached = cacheable ? readEntry(key) : null;

  const [state, setState] = useState(() => ({
    data: cached?.data ?? null,
    error: null,
    loading: !cached,
    refreshing: false,
    lastUpdated: cached?.fetchedAt ?? null,
  }));

  const requestIdRef = useRef(0);
  const mounted = useRef(true);

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
        loading: fromCache || silent ? s.loading : true,
        refreshing: silent ? s.refreshing : fromCache || s.data !== null,
        error: silent ? s.error : null,
      }));

      const result = await dedupe(key, () => fetcherRef.current());

      if (requestId !== requestIdRef.current) return;
      if (!mounted.current) return;

      if (!result?.ok) {
        setState((s) => ({
          ...s,
          loading: false,
          refreshing: false,
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
  }, [key, enabled, cacheable, run]);

  const refresh = useCallback(() => run({ fromCache: true }), [run]);

  const revalidate = useCallback(() => run({ silent: true }), [run]);

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
