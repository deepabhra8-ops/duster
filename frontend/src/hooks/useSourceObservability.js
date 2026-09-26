import { useCallback } from "react";
import { getSourceObservability } from "../services/dataSourcesService.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";

export function useSourceObservability(sourceName) {
  const { username } = useAuth();
  const key = buildKey(username, "source-observability", { source: sourceName || "" });
  const fetcher = useCallback(() => getSourceObservability(sourceName), [sourceName]);

  return useCachedResource({ key, fetcher, enabled: Boolean(sourceName) });
}

export default useSourceObservability;
