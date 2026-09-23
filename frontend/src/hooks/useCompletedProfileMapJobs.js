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
