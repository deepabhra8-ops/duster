import { fmtDate } from "../utils/helpers.js";
import { STATUS_PILL } from "../constants/jobStatus.js";
import Pagination from "./Pagination.jsx";
import { IconError, IconChart } from "./Icons.jsx";

function statusPill(status) {
  return STATUS_PILL[status] || "pill-amber";
}

function completionDate(job) {
  const v = job.finished ?? job.completed_at ?? job.completion_date ?? job.ended ?? null;
  return v ? fmtDate(v) : "";
}

export default function JobsTable({
  jobs = [],
  total = 0,
  loading,
  error,
  page,
  totalPages,
  onPage,
  onViewLog,
  onDownload,
}) {
  if (loading) return <p className="empty-state">Loading…</p>;
  if (error) return <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> Cannot reach API ({error})</div>;
  if (jobs.length === 0) return <p className="empty-state">No jobs yet.</p>;

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <div className="table-scroll">
          <table className="tbl profile-map-table redesigned">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Project</th>
                <th>Status</th>
                <th>Created Date</th>
                <th>Completion Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} style={j.archived ? { opacity: 0.6 } : undefined}>
                  <td>
                    <span className="mono">{j.job_id}</span>
                  </td>
                  <td>{j.project || "–"}</td>
                  <td>
                    <span className={`pill ${statusPill(j.status)}`}>{j.status}</span>
                  </td>
                  <td className="hint">{fmtDate(j.started)}</td>
                  <td className="hint">{completionDate(j)}</td>
                  <td>
                    <div className="file-action-btns">
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => onViewLog(j.job_id)}>
                        📋 Log
                      </button>
                      {j.status === "done" && (
                        <button type="button" className="btn btn-teal btn-sm" onClick={() => onDownload(j.job_id, "report")}>
                          <IconChart style={{ verticalAlign: "text-bottom" }} /> Report
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="hint" style={{ marginTop: "8px" }}>
        Showing {jobs.length} of {total} job(s)
      </p>

      <Pagination page={page} totalPages={totalPages} onPage={onPage} />
    </>
  );
}
