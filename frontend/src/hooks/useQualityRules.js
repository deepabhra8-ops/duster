import { useCallback } from "react";
import { getRule, getRuleLibrary, getRunResults } from "../services/qualityRulesService.js";
import { useAuth } from "./useAuth.js";
import { useCachedResource } from "./useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";

export function useRuleLibrary() {
  const { username } = useAuth();
  const key = buildKey(username, "quality-rule-library", {});
  const fetcher = useCallback(() => getRuleLibrary(), []);

  return useCachedResource({ key, fetcher });
}

export function useRule(ruleName) {
  const { username } = useAuth();
  const key = buildKey(username, "quality-rule", { rule: ruleName || "" });
  const fetcher = useCallback(() => getRule(ruleName), [ruleName]);

  return useCachedResource({ key, fetcher, enabled: Boolean(ruleName) });
}

export function useRunResults(runId) {
  const { username } = useAuth();
  const key = buildKey(username, "quality-run-results", { run: runId || "" });
  const fetcher = useCallback(() => getRunResults(runId), [runId]);

  return useCachedResource({ key, fetcher });
}
