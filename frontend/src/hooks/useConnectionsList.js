import { useCallback } from "react";
import { listConnectionsSummary } from "../services/connectionsService.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";

export function useConnectionsList() {
  const { username } = useAuth();
  const key = buildKey(username, "connections-summary", {});
  const fetcher = useCallback(() => listConnectionsSummary(), []);

  return useCachedResource({ key, fetcher });
}

export default useConnectionsList;
