import { fetchDashboardSummary } from "../api/api.js";

/**
 * Normalizes /api/dashboard/summary into the shape ControlRoomPage consumes.
 * Only this file (and connectionsService.js) is allowed to import api/api.js —
 * pages and hooks depend on this service, never on the axios client directly.
 */
export async function getSummary() {
  const { ok, data, error } = await fetchDashboardSummary();
  if (!ok) return { ok, error };

  return {
    ok: true,
    data: {
      jobsTotal: data?.jobs?.total ?? 0,
      jobsActive: data?.jobs?.active ?? 0,
      connectionsCount: data?.connections ?? 0,
      latestScore: data?.latest_score ?? null,
      scoreTrend: data?.score_trend ?? [],
      recentJobs: data?.recent_jobs ?? [],
    },
  };
}

export default { getSummary };
