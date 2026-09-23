import { STEPS } from "../../constants/appConfig.js";
import { IconTag } from "../Icons.jsx";

export default function ProjectSettings({ config, onChange }) {
  const runMode = Number(config.run_mode ?? 1);
  const isCuration = runMode === 2;

  const handleRunModeChange = (e) => {
    const nextRunMode = Number(e.target.value);
    const patch = { run_mode: nextRunMode };
    if (nextRunMode === 2 && String(config.step) === STEPS.STEP1) {
      patch.step = STEPS.STEP3;
    }
    onChange(patch);
  };

  return (
    <div className="card">
      <div className="card-title"><IconTag style={{ verticalAlign: "text-bottom" }} /> Project Settings</div>
      <div className="form-grid cols3">
        <div className="form-group">
          <label htmlFor="cfg-project">Project Name</label>
          <input
            id="cfg-project"
            type="text"
            placeholder="MyProject"
            autoComplete="off"
            value={config.project_name ?? ""}
            onChange={(e) => onChange({ project_name: e.target.value })}
          />
        </div>

        <div className="form-group">
          <label htmlFor="cfg-mode">Run Mode</label>
          <select id="cfg-mode" value={String(runMode)} onChange={handleRunModeChange}>
            <option value="1">Mode 1 - Profiling Only</option>
            <option value="2">Mode 2 - Curation (valid rows → staging)</option>
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="cfg-step">Pipeline Step</label>
          <select
            id="cfg-step"
            value={config.step ?? STEPS.STEP1}
            onChange={(e) => onChange({ step: e.target.value })}
          >
            <option value={STEPS.STEP1} disabled={isCuration}>
              Step 1 - Profile Mapper{isCuration ? " (not available in Curation mode)" : ""}
            </option>
            <option value={STEPS.STEP3}>Step 3 - DQ Validator</option>
          </select>
        </div>
      </div>
    </div>
  );
}
