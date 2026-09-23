import { useCallback } from "react";
import { getSummary } from "../services/dashboardService.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";

export function useDashboardSummary() {
  const { username } = useAuth();
  const key = buildKey(username, "dashboard", {});
  const fetcher = useCallback(() => getSummary(), []);

  return useCachedResource({ key, fetcher });
}

export default useDashboardSummary;
