-- =============================================================
-- 004 - Widen validation_results.overall_score
-- =============================================================
--
-- overall_score holds a 0..1 fraction (build_summary rounds it to 4 decimal
-- places), not a percentage. NUMERIC(5,2) therefore quantized every score to
-- 0.01 - one whole percentage point - which is the entire resolution of the
-- dashboard's score trend and "latest score per lineage", both of which read
-- this column rather than the JSON summary.
--
-- Worse than coarse: it moved scores across a threshold. A run scoring 0.9470
-- stored as 0.95, which is exactly DimensionScorer.GOOD_THRESHOLD, so a run
-- that was genuinely below "Good" displayed as Good on the dashboard.
--
-- NUMERIC(6,4) holds the 4 decimal places build_summary actually produces, with
-- room to spare for anything that ever stores a percentage here by mistake.
-- The cast is exact-to-wider, so existing rows are preserved as-is - they keep
-- whatever precision they were already truncated to; only new runs gain the
-- extra digits.
-- =============================================================

BEGIN;

ALTER TABLE validation_results
    ALTER COLUMN overall_score TYPE NUMERIC(6, 4);

COMMIT;
