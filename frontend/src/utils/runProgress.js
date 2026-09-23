/**
 * runProgress.js - Per-flow stage/progress derivation for the Run pages.
 *
 * Each backend job runs exactly one pipeline step - pipeline_service.py's
 * run_job() is an if/elif on `step`, never both in the same job - so a
 * single shared 4-stage indicator (Profile Mapper → Analyst Review →
 * DQ Validator → Report Ready) never matched what a given job actually
 * did: a Step 3 job would sit at 0% with "Profile Mapper" shown as the
 * active stage the whole run, then jump straight to 50% on completion.
 *
 * These two functions build a small stage list per flow, driven only by
 * the log markers that flow's job type actually emits, so the *label*
 * shown always matches the job in view (StageIndicator's step circles).
 *
 * The *percentage* bar is a separate concern: pipeline_service.py now
 * reports real `{current, total}` checkpoints (one per table processed,
 * via a progress_callback threaded down into ValidationEngine/
 * ProfilingEngine's per-table loops) onto job.progress, polled the same
 * way as the log. When that's present we use it directly instead of the
 * coarse two-or-three-step count below, so the bar advances once per
 * table rather than jumping straight from 0% to the end. The step-count
 * fallback only kicks in for a job with no `progress` yet (e.g. one
 * created before this field existed, or read the instant after submit).
 */

function deriveProgressPct(progress, isFinal, fallbackPct) {
  if (isFinal) return 100;

  const total = progress?.total ?? 0;
  if (total > 0) {
    const current = progress?.current ?? 0;
    // Capped below 100 while still running - the job's own "total" unit
    // lands the instant the report/profile-map is saved, a moment before
    // status actually flips to "done", so this avoids a 100% flash pre-completion.
    return Math.max(0, Math.min(99, Math.round((current / total) * 100)));
  }

  return fallbackPct;
}

function finalize(steps, finalLabel, isFinal, progress) {
  const connectors = steps.slice(0, -1).map((s) => s.state === "done");
  const doneCount = steps.filter((s) => s.state === "done").length;
  const checkpointPct = Math.round((doneCount / steps.length) * 100);
  const progressPct = deriveProgressPct(progress, isFinal, checkpointPct);
  const active = steps.find((s) => s.state === "active");
  const lastDone = [...steps].reverse().find((s) => s.state === "done");
  const currentStage = isFinal ? finalLabel : active?.label || lastDone?.label || "Not started";
  return { steps, connectors, progressPct, currentStage };
}

/** Step 1 - Profile Mapper: only "start" and "saved" signals exist. */
export function computeProfileMapperProgress(status, log = [], progress = null) {
  const logStr = (log || []).join(" ");
  const running = status === "running";
  const final = status === "done";
  const mapSaved = logStr.includes("Profile Map saved");

  const steps = [
    { num: "1", label: "Profile Mapper", state: mapSaved ? "done" : running ? "active" : "pending" },
    { num: "✓", label: "Profile Map Ready", state: final ? "done" : "pending" },
  ];

  return finalize(steps, "Profile Map Ready", final, progress);
}

/**
 * Step 3 - DQ Validator: "start", "report saved", and - only in Curation
 * (Run Mode 2) - a distinct "staging output" signal once passing rows are
 * written to staging.
 */
export function computeValidatorProgress(status, log = [], isCuration = false, progress = null) {
  const logStr = (log || []).join(" ");
  const running = status === "running";
  const final = status === "done";
  const reportSaved = logStr.includes("DQ Report saved");
  const staged = logStr.includes("Staging output");

  const steps = [
    { num: "1", label: "DQ Validator", state: reportSaved ? "done" : running ? "active" : "pending" },
    { num: "2", label: "Report Generated", state: reportSaved ? "done" : "pending" },
  ];

  if (isCuration) {
    steps.push({
      num: "3",
      label: "Data Staged",
      state: staged ? "done" : reportSaved && running ? "active" : "pending",
    });
  }

  steps.push({ num: "✓", label: "Complete", state: final ? "done" : "pending" });

  return finalize(steps, "Complete", final, progress);
}
