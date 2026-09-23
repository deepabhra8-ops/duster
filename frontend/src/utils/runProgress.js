function deriveProgressPct(progress, isFinal, fallbackPct) {
  if (isFinal) return 100;

  const total = progress?.total ?? 0;
  if (total > 0) {
    const current = progress?.current ?? 0;
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
