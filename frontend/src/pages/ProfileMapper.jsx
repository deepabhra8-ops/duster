import { useState } from "react";
import { CircleX, Play, Plus, Trash2, Eye } from "lucide-react";
import RefreshButton from "../components/RefreshButton.jsx";
import { Link, useNavigate } from "react-router-dom";
import NewProfileMapperJobModal from "../components/profileMapper/NewProfileMapperJobModal.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Pagination from "../components/Pagination.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import StatusPill from "../components/StatusPill.jsx";
import JobErrorButton from "../components/JobErrorButton.jsx";
import { PAGE_META } from "../constants/appConfig.js";
import { DATABASE_TYPE_OPTIONS } from "../constants/sourceTypes.js";
import { cancelJob, deleteJob, startJob } from "../api/api.js";
import { IconError } from "../components/Icons.jsx";
import { derivePercent } from "../utils/jobProgress.js";
import { friendlyStartError } from "../utils/helpers.js";
import { STATUS_PROGRESS_COLOR, ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { useJobList } from "../hooks/useJobList.js";
import { useToast } from "../hooks/useToast.js";

const DB_TYPE_LABELS = Object.fromEntries(DATABASE_TYPE_OPTIONS.map((o) => [o.value, o.label]));

function jobTypeLabel(job) {
  return DB_TYPE_LABELS[job.databaseType] || job.databaseType || "-";
}

export default function ProfileMapper() {
  const meta = PAGE_META["profile-mapper"];
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [newJobOpen, setNewJobOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [confirmState, setConfirmState] = useState(null);

  const {
    state,
    reload: load,
    refreshing,
    lastUpdated,
    invalidateAndReload,
    page,
    setPage,
    searchInput,
    setSearchInput,
    statusFilter,
    setStatusFilter,
    dbTypeFilter,
    setDbTypeFilter,
    sortOrder,
    setSortOrder,
    pageSize,
    setPageSize,
  } = useJobList({
    step: "1",
    doneMessage: "completed successfully. Click View Results to see the profile map.",
  });

  async function handleRun(job) {
    setBusyId(job.job_id);
    const { ok, error } = await startJob(job.job_id);
    setBusyId(null);
    if (!ok) {
      showToast({ type: "error", title: "Can't start this job", message: friendlyStartError(error) });
      return;
    }
    showToast({ type: "info", title: "Job started", message: `"${job.name || job.job_id}" is now running.` });
    invalidateAndReload();
  }

  function handleViewResults(jobId) {
    navigate(`/profile-mapper/${jobId}`);
  }

  async function handleCancel(jobId) {
    setBusyId(jobId);
    const { ok, error } = await cancelJob(jobId);
    setBusyId(null);
    if (!ok) {
      showToast({ type: "error", title: "Couldn't cancel job", message: error || "Failed to cancel job." });
      return;
    }
    invalidateAndReload();
  }

  async function handleDelete(jobId, name) {
    setConfirmState({ jobId, name });
  }

  async function confirmDelete() {
    if (!confirmState) return;
    const { jobId, name } = confirmState;
    setConfirmState(null);
    setBusyId(jobId);
    const { ok, error } = await deleteJob(jobId);
    setBusyId(null);
    if (!ok) {
      showToast({ type: "error", title: "Couldn't delete job", message: error || "Failed to delete job." });
      return;
    }
    invalidateAndReload();
  }

  return (
    <section>
      <header className="page-header">
        <h2>{meta.title}</h2>
        <p>{meta.subtitle}</p>
      </header>

      <div className="profile-mapper-main page-fill">
        <div className="card">
          <div className="uploads-toolbar">
            <input
              type="text"
              className="search-input jobs-toolbar-search"
              placeholder="Search by Job Name or Job ID…"
              autoComplete="off"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            <div className="filter-group">
              <select
                className="filter-select"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="queued">Queued</option>
                <option value="running">In-Progress</option>
                <option value="cancelling">Cancelling</option>
                <option value="done">Completed</option>
                <option value="error">Error</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <select
                className="filter-select"
                value={dbTypeFilter}
                onChange={(e) => {
                  setDbTypeFilter(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by database type"
              >
                <option value="">All Database Types</option>
                {DATABASE_TYPE_OPTIONS.filter((o) => o.value).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <select
                className="filter-select"
                value={sortOrder}
                onChange={(e) => {
                  setSortOrder(e.target.value);
                  setPage(1);
                }}
              >
                <option value="desc">↓ Newest first</option>
                <option value="asc">↑ Oldest first</option>
              </select>
            </div>
            <div className="jobs-toolbar-action row" style={{ gap: "8px", alignItems: "center" }}>
              <RefreshButton onRefresh={load} refreshing={refreshing} lastUpdated={lastUpdated} />
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setNewJobOpen(true)}
              >
                <Plus size={16} aria-hidden="true" />
                New Job
              </button>
            </div>
          </div>

          <div className="profile-mapper-table">
            {state.error ? (
              <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> {state.error}</div>
            ) : (
              <>
                <div className="profile-mapper-table-scroll jobs-table-scroll">
                  <table className="tbl profile-map-table redesigned jobs-list-table">
                    <thead>
                      <tr>
                        <th>Job ID</th>
                        <th>Name</th>
                        <th>Description</th>
                        <th style={{ paddingLeft: "32px" }}>Connection</th>
                        <th style={{ paddingLeft: "32px" }}>DB Type</th>
                        <th style={{ paddingLeft: "32px" }}>Status</th>
                        <th style={{ paddingLeft: "32px" }}>Progress</th>
                        <th style={{ paddingLeft: "32px" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.loading ? (
                        <tr>
                          <td colSpan={8} className="empty-state">
                            Loading…
                          </td>
                        </tr>
                      ) : state.jobs.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="empty-state">
                            {searchInput || statusFilter || dbTypeFilter
                              ? "No jobs match your search/filter."
                              : "No jobs yet. Click \"New Job\" to create one."}
                          </td>
                        </tr>
                      ) : (
                        state.jobs.map((j) => {
                          const canCancel = j.status === "queued" || j.status === "running";
                          const canDelete = !ACTIVE_STATUSES.includes(j.status);
                          const canRun = j.status === "draft";
                          const canViewResults = j.status === "done";
                          return (
                            <tr key={j.job_id}>
                              <td className="job-id-cell" data-label="Job ID">
                                <Link to={`/profile-mapper/${j.job_id}`} className="mono link" title={j.job_id}>
                                  {j.job_id}
                                </Link>
                              </td>
                              <td className="job-name-cell" data-label="Name" title={j.name || j.project || ""}>{j.name || j.project}</td>
                              <td className="job-desc-cell hint" data-label="Description" title={j.description || ""}>
                                {j.description || "—"}
                              </td>
                              <td className="job-name-cell" style={{ paddingLeft: "32px" }} data-label="Connection" title={j.connectionName || ""}>
                                {j.connectionName || "—"}
                              </td>
                              <td style={{ paddingLeft: "32px" }} data-label="DB Type">
                                <span className="pill pill-blue">{jobTypeLabel(j)}</span>
                              </td>
                              <td style={{ paddingLeft: "32px" }} data-label="Status">
                                <span className="status-with-error">
                                  <StatusPill status={j.status} />
                                  {j.status === "error" ? (
                                    <JobErrorButton jobId={j.job_id} jobName={j.name || j.project} />
                                  ) : null}
                                </span>
                              </td>
                              <td style={{ paddingLeft: "32px" }} data-label="Progress">
                                <ProgressBar
                                  percent={derivePercent(j.progress, j.status)}
                                  colorVar={STATUS_PROGRESS_COLOR[j.status] || "--mgray"}
                                />
                              </td>
                              <td style={{ paddingLeft: "32px" }} data-label="Actions">
                                <div className="file-action-btns file-action-btns-compact">
                                  <button
                                    type="button"
                                    className="btn btn-ghost btn-icon-only"
                                    disabled={!canRun || busyId === j.job_id}
                                    onClick={() => handleRun(j)}
                                    aria-label="Run"
                                    title={canRun ? "Run" : "Only a draft job can be run from here"}
                                  >
                                    <Play size={16} aria-hidden="true" />
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-ghost btn-icon-only"
                                    disabled={!canViewResults}
                                    onClick={() => handleViewResults(j.job_id)}
                                    aria-label="View results"
                                    title={canViewResults ? "View results" : "Available once the job has finished"}
                                  >
                                    <Eye size={16} aria-hidden="true" />
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-ghost btn-icon-only"
                                    disabled={!canCancel || busyId === j.job_id}
                                    onClick={() => handleCancel(j.job_id)}
                                    aria-label="Cancel"
                                    title="Cancel"
                                  >
                                    <CircleX size={16} aria-hidden="true" />
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-danger btn-icon-only"
                                    disabled={!canDelete || busyId === j.job_id}
                                    onClick={() => handleDelete(j.job_id, j.name)}
                                    aria-label="Delete"
                                    title="Delete"
                                  >
                                    <Trash2 size={16} aria-hidden="true" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>

                <Pagination
                  page={page}
                  totalPages={state.totalPages}
                  onPage={setPage}
                  total={state.total}
                  pageSize={pageSize}
                  onPageSize={setPageSize}
                  noun="jobs"
                />
              </>
            )}
          </div>
        </div>
      </div>

      <NewProfileMapperJobModal
        open={newJobOpen}
        onClose={() => setNewJobOpen(false)}
        onCreated={() => {
          setPage((p) => {
            if (p !== 1) return 1;
            invalidateAndReload();
            return 1;
          });
        }}
      />

      <ConfirmDialog
        open={Boolean(confirmState)}
        title="Delete Job"
        subject={confirmState?.name || confirmState?.jobId}
        message="This will permanently delete the job and its results. This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setConfirmState(null)}
      />
    </section>
  );
}
