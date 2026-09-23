/**
 * DownloadPanel.jsx - Artifact downloads for a completed job.
 *
 * Each button is enabled only when its corresponding flag is true:
 *   Report  → has_report
 *   Profile → has_profile
 *   Staging → has_staging
 * Clicking opens the backend download URL in a new tab.
 */
import { downloadUrl } from "../api/api.js";
import { openInNewTab } from "../utils/helpers.js";
import { IconChart, IconMap, IconArchive } from "./Icons.jsx";

export default function DownloadPanel({ job, jobId }) {
  if (!job) return null;

  const download = (kind) => {
    if (jobId) openInNewTab(downloadUrl(jobId, kind));
  };

  return (
    <div className="card" id="download-card">
      <div className="card-title">📥 Downloads</div>
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-teal"
          disabled={!job.has_report}
          onClick={() => download("report")}
        >
          <IconChart style={{ verticalAlign: "text-bottom" }} /> Download DQ Report (.xlsx)
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!job.has_profile}
          onClick={() => download("profile")}
        >
          <IconMap style={{ verticalAlign: "text-bottom" }} /> Download Profile Map (.xlsx)
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!job.has_staging}
          onClick={() => download("staging")}
        >
          <IconArchive style={{ verticalAlign: "text-bottom" }} /> Download Staging (.zip)
        </button>
      </div>
    </div>
  );
}
