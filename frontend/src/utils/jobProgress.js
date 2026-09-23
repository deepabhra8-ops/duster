export function derivePercent(progress, status) {
  if (status === "done") return 100;
  const total = progress?.total ?? 0;
  if (total <= 0) return 0;
  const current = progress?.current ?? 0;
  return Math.max(0, Math.min(99, Math.round((current / total) * 100)));
}

export default derivePercent;
