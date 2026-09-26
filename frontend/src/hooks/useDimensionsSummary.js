import { useCallback } from "react";
import { getDimensionsSummary } from "../services/dimensionsService.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";

export function useDimensionsSummary() {
  const { username } = useAuth();
  const key = buildKey(username, "dashboard-dimensions", {});
  const fetcher = useCallback(() => getDimensionsSummary(), []);

  return useCachedResource({ key, fetcher });
}

export default useDimensionsSummary;
