/**
 * useCompletedProfileMapJobs.js - fetches completed ("done") Profile Mapper
 * jobs, shaped as SearchableSelect options ({ value, label }).
 *
 * Same shape/pattern as useSavedConnections.js (fetch on every `open`
 * transition to true, not cached across opens - always-fresh beats a stale
 * list here, e.g. a job finishing since the modal last opened). Built for
 * NewValidatorJobModal.jsx's "Select Profile Map" dropdown: a DQ Validator
 * run needs a finished Profile Mapper job's profile map to validate
 * against, so only step "1" (Profile Mapper, see listJobs' own doc comment)
 * jobs with status "done" are offered.
 *
 * pageSize 200 rather than JOBS_PAGE_SIZE (10, the jobs *table*'s page
 * size) - this dropdown has no pagination UI of its own, so it asks for
 * enough in one request to stand in for "all of them"; fine for how few
 * completed jobs this app expects for now, same "list is small/cheap"
 * assumption useSavedConnections.js makes for saved connections.
 */
import { useEffect, useState } from "react";
import { listJobs } from "../api/api.js";

export function useCompletedProfileMapJobs(open) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    listJobs({ step: "1", status: "done", pageSize: 200 }).then(({ ok, data, error: err }) => {
      if (cancelled) return;
      setLoading(false);
      if (!ok) {
        setError(err || "Failed to load completed Profile Mapper jobs");
        setOptions([]);
        return;
      }
      const jobs = data?.jobs || [];
      setOptions(jobs.map((j) => ({ value: j.job_id, label: `${j.job_id} - ${j.name || "Untitled Job"}` })));
    });

    return () => {
      cancelled = true;
    };
  }, [open]);

  return { options, loading, error };
}

export default useCompletedProfileMapJobs;
