import { useEffect, useState } from "react";
import { listConnections } from "../api/api.js";

export function useSavedConnections(open) {
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    listConnections().then(({ ok, data, error: err }) => {
      if (cancelled) return;
      setLoading(false);
      if (!ok) {
        setError(err || "Failed to load saved connections");
        setOptions([]);
        return;
      }
      const rows = data?.data || [];
      setOptions(rows.map((c) => ({ value: c.id, label: `${c.name} (${c.db_type})`, dbType: c.db_type })));
    });

    return () => {
      cancelled = true;
    };
  }, [open]);

  return { options, loading, error };
}

export default useSavedConnections;
