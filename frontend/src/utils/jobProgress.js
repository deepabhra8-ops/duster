/**
 * jobProgress.js - derives a 0-100% number from a job's real `progress`
 * field ({current, total} - one tick per table finished, see
 * pipeline_service.py) and `status`. Same clamp-at-99%-while-running logic
 * runProgress.js's (unexported) deriveProgressPct() already uses for the
 * existing Run pages - shared here since both ProfileMapper.jsx and
 * ProfileMapperJob.jsx need it and that function isn't exported.
 */
export function derivePercent(progress, status) {
  if (status === "done") return 100;
  const total = progress?.total ?? 0;
  if (total <= 0) return 0;
  const current = progress?.current ?? 0;
  return Math.max(0, Math.min(99, Math.round((current / total) * 100)));
}

export default derivePercent;
