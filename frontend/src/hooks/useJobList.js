/**
 * useJobList.js - the jobs-list state shared by the Profile Mapper and
 * Validator landing pages: paging, debounced search, status/database-type
 * filters, sort, the
 * server fetch, and the silent poll that keeps active jobs moving.
 *
 * These two pages ran byte-identical copies of this logic - the two `load`
 * implementations differed only in `step` ("1" vs "3") and one toast message.
 * Every fix therefore had to be made twice, and drift between them was silent.
 *
 * Fetching is delegated to useCachedResource, which owns the sessionStorage
 * cache, the in-flight dedupe, and the response sequencing that stops a slow
 * page-1 answer overwriting the page-2 the user has already moved to. This hook
 * keeps the list-specific parts: paging, the debounced search, the
 * active -> terminal toasts, and the silent poll.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listJobs } from "../api/api.js";
import { DEBOUNCE_DELAY, JOB_POLL_INTERVAL, JOBS_PAGE_SIZE } from "../constants/appConfig.js";
import { ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey, invalidate, resourcePrefix } from "../utils/pageCache.js";
import { useToast } from "./useToast.js";

// A single frozen array, so the empty case has a stable identity. `|| []` inline
// mints a new array on every render, which would change the poll effect's
// dependency every render and make it clear and re-arm its interval endlessly.
const NO_JOBS = Object.freeze([]);

/**
 * Drop every cached page of every jobs list, for this user.
 *
 * Offset pagination means one mutation invalidates more than the page on
 * screen: deleting a job shifts every later page, and a job started on the
 * Profile Mapper list changes the Validator list's source data. Exported so the
 * pages can call it straight after a start/cancel/delete.
 */
export function invalidateJobLists(username) {
  invalidate(resourcePrefix(username, "jobs"));
  invalidate(resourcePrefix(username, "dashboard"));
}

/**
 * @param {object}   options
 * @param {string}   options.step           "1" for Profile Mapper jobs, "3" for Validator jobs.
 * @param {string}   options.doneMessage    Toast body when a job of this kind finishes.
 */
export function useJobList({ step, doneMessage }) {
  const { showToast } = useToast();
  const { username } = useAuth();

  const [page, setPage] = useState(1);
  /* Rows per page is the user's choice now, not a fixed constant - the list
     footer offers it. JOBS_PAGE_SIZE stays the default. It is part of the cache
     key and the request below, so switching sizes refetches rather than
     re-slicing a page the server already trimmed. */
  const [pageSize, setPageSizeState] = useState(JOBS_PAGE_SIZE);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dbTypeFilter, setDbTypeFilter] = useState("");
  const [sortOrder, setSortOrder] = useState("desc");

  // job_id -> status last observed, purely to detect an active -> terminal
  // transition during silent polling. Never read for anything else, so a ref
  // rather than state.
  const prevStatusesRef = useRef(new Map());

  // The stale-response guard that used to live here (a monotonic request id, so
  // a slow page-1 answer could not overwrite the page-2 the user moved to) now
  // lives in useCachedResource, which owns the fetching.

  /* Debounce search → reset to page 1. */
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, DEBOUNCE_DELAY);
    return () => clearTimeout(t);
  }, [searchInput]);

  const announceFinishedJobs = useCallback(
    (jobs) => {
      const prevStatuses = prevStatusesRef.current;

      for (const job of jobs) {
        const prevStatus = prevStatuses.get(job.job_id);
        const justFinished =
          prevStatus &&
          ACTIVE_STATUSES.includes(prevStatus) &&
          !ACTIVE_STATUSES.includes(job.status);

        if (!justFinished) continue;

        const label = job.name || job.job_id;

        if (job.status === "done") {
          showToast({ type: "success", title: "Job finished", message: `"${label}" ${doneMessage}` });
        } else if (job.status === "error") {
          showToast({
            type: "error",
            title: "Job failed",
            message: `"${label}" ran into a problem and didn't finish. Open it to check the log for details.`,
          });
        } else if (job.status === "cancelled") {
          showToast({ type: "warn", title: "Job cancelled", message: `"${label}" was cancelled.` });
        }
      }

      prevStatusesRef.current = new Map(jobs.map((job) => [job.job_id, job.status]));
    },
    [showToast, doneMessage]
  );

  // Cached per query. Every input that changes the response is in the key, so
  // paging back and forth is served from sessionStorage instead of the network.
  const cacheKey = buildKey(username, "jobs", {
    step,
    page,
    pageSize,
    search,
    status: statusFilter,
    dbType: dbTypeFilter,
    sortOrder,
  });

  const fetcher = useCallback(
    () =>
      listJobs({
        page,
        pageSize,
        search,
        status: statusFilter,
        dbType: dbTypeFilter,
        sortBy: "started",
        sortOrder,
        step,
      }),
    [page, pageSize, search, statusFilter, dbTypeFilter, sortOrder, step]
  );

  const select = useCallback(
    (data) => ({
      jobs: data?.jobs || [],
      total: data?.total || 0,
      totalPages: data?.totalPages || 1,
    }),
    []
  );

  const {
    data,
    error,
    loading,
    refreshing,
    lastUpdated,
    refresh,
    revalidate,
  } = useCachedResource({ key: cacheKey, fetcher, select });

  const state = useMemo(
    () => ({
      jobs: data?.jobs || NO_JOBS,
      total: data?.total || 0,
      totalPages: data?.totalPages || 1,
      loading,
      error,
    }),
    [data, loading, error]
  );

  // Toasts on active -> terminal transitions, driven by whatever the latest
  // response was, cached or fresh.
  useEffect(() => {
    if (data?.jobs) announceFinishedJobs(data.jobs);
  }, [data, announceFinishedJobs]);

  /**
   * Backend heartbeat: while any visible job is still active, keep the list
   * moving. Deliberately `revalidate` (silent) rather than `refresh` - this
   * fires every 1400 ms, and spinning the refresh icon on every tick would be
   * noise. It still writes through to the cache, so leaving the page and coming
   * back shows current data rather than the state at first paint.
   */
  useEffect(() => {
    if (!state.jobs.some((job) => ACTIVE_STATUSES.includes(job.status))) return undefined;
    const t = setInterval(revalidate, JOB_POLL_INTERVAL);
    return () => clearInterval(t);
  }, [state.jobs, revalidate]);

  return {
    state,
    reload: refresh,
    refreshing,
    lastUpdated,
    /** Clear every cached jobs page, then refetch - for after a mutation. */
    invalidateAndReload: useCallback(() => {
      invalidateJobLists(username);
      refresh();
    }, [username, refresh]),
    page,
    setPage,
    pageSize,
    /* Back to page 1 on every change: page 4 of 10-row pages is page 2 of
       25-row pages, and keeping the number would silently move the user
       somewhere they did not ask to go - or past the end of the list. */
    setPageSize: useCallback((size) => {
      setPageSizeState(size);
      setPage(1);
    }, []),
    searchInput,
    setSearchInput,
    statusFilter,
    setStatusFilter,
    dbTypeFilter,
    setDbTypeFilter,
    sortOrder,
    setSortOrder,
  };
}
