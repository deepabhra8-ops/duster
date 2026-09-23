/**
 * useSavedConnections.js - fetches real saved connections, shaped as
 * SearchableSelect options ({ value, label }).
 *
 * Shared by NewProfileMapperJobModal.jsx and NewValidatorJobModal.jsx (both
 * previously used a hardcoded MOCK_CONNECTIONS array) so the fetch +
 * label-shaping logic exists in exactly one place rather than duplicated
 * per modal - same GET /api/connections call and "{name} ({db_type})"
 * label format NewJobWizardModal.jsx already uses for its own connection
 * picker.
 *
 * Fetches on every `open` transition to true (not cached across opens) -
 * the list is small/cheap, and always-fresh beats a stale cache here,
 * e.g. if a connection was created or deleted since the modal last opened.
 */
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
      // dbType rides along on each option (SearchableSelect only reads
      // value/label, so this is inert there) so a consumer can look up the
      // chosen connection's db type without a second fetch/lookup.
      setOptions(rows.map((c) => ({ value: c.id, label: `${c.name} (${c.db_type})`, dbType: c.db_type })));
    });

    return () => {
      cancelled = true;
    };
  }, [open]);

  return { options, loading, error };
}

export default useSavedConnections;
