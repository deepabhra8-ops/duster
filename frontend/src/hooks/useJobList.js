import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listJobs } from "../api/api.js";
import { DEBOUNCE_DELAY, JOB_POLL_INTERVAL, JOBS_PAGE_SIZE } from "../constants/appConfig.js";
import { ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey, invalidate, resourcePrefix } from "../utils/pageCache.js";
import { useToast } from "./useToast.js";

const NO_JOBS = Object.freeze([]);

export function invalidateJobLists(username) {
  invalidate(resourcePrefix(username, "jobs"));
  invalidate(resourcePrefix(username, "dashboard"));
}

export function useJobList({ step, doneMessage }) {
  const { showToast } = useToast();
  const { username } = useAuth();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(JOBS_PAGE_SIZE);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dbTypeFilter, setDbTypeFilter] = useState("");
  const [sortOrder, setSortOrder] = useState("desc");

  const prevStatusesRef = useRef(new Map());

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

  useEffect(() => {
    if (data?.jobs) announceFinishedJobs(data.jobs);
  }, [data, announceFinishedJobs]);

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
    invalidateAndReload: useCallback(() => {
      invalidateJobLists(username);
      refresh();
    }, [username, refresh]),
    page,
    setPage,
    pageSize,
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
