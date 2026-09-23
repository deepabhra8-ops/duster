/**
 * ProfileMapper.jsx - Profile Map landing page.
 *
 * One card holding a `.uploads-toolbar` (search + two filter dropdowns +
 * search, left-aligned, then New Job pushed to the extreme right) stacked
 * above a `.profile-mapper-table` div - layout otherwise unchanged from
 * the original design pass (see docs/ux-plan.md §5).
 *
 * Rows are real again: GET /api/jobs?step=1 (JobRepository/JobService),
 * filtered to Profile Mapper jobs and enriched with name/description/
 * databaseType/connectionName/sourceType/progress (see job_service.py's
 * list_jobs) - search/status/database-type-filter/sort/pagination are all
 * server-side, same
 * debounced-search + load-callback pattern Jobs.jsx uses. The "DB Type"
 * column reads jobTypeLabel(job): "Flat File" for
 * a flat-file job (sourceType - added to list_jobs alongside the
 * already-there databaseType, exactly so this column could tell the two
 * apart), else the resolved database type's label (DB_TYPE_LABELS) - was
 * blank/"-" for flat-file jobs before, since they have no databaseType.
 * Was mocked for a stretch
 * (MOCK_PROFILE_MAPPER_JOBS, constants/mockProfileMapperJobs.js) while the
 * "New Job" modal's own backend wiring was being built out; switched back
 * now that Create actually needs a newly-made job to show up here and be
 * reachable at /profile-mapper/:jobId, which a static mock array can't do.
 * Cancel and Delete are real again too (cancelJob/deleteJob), matching
 * backend's own status guards (cancel: queued/running only; delete:
 * anything except queued/running/cancelling).
 *
 * Status vocabulary matches the real one: draft (created, not started) →
 * queued/running → done, or → error, or → cancelling → cancelled. There
 * is no "paused" - the backend has no pause capability, only cancel (see
 * ProfileMapperJob.jsx's header comment) - so table rows have no Pause
 * button. The status pill and the filter dropdown both display these
 * through jobStatusLabel() (helpers.js - shared with Validator.jsx's own
 * jobs table) rather than the raw value, e.g. "running" reads "In-Progress".
 *
 * The table (header included) always renders once loaded, even with zero
 * rows - only a genuine fetch error swaps it out for the alert. An empty
 * result shows a message *inside* the table (one <td colSpan={8}>, matching
 * the header's column count) rather than hiding the header/toolbar, so the
 * columns stay visible instead of the page looking broken - worded
 * depending on *why* it's empty: "No jobs yet…" when no search/filter is
 * active (there simply are no jobs), "No jobs match your search/filter."
 * when one is (search and/or statusFilter non-empty), so a user who hasn't
 * touched either isn't told to go check filters they never set. Loading
 * state renders the same way - the header
 * stays put and only the body's row swaps to "Loading…" - rather than
 * blanking the whole card, which used to jump the toolbar/pagination
 * position on every fetch. NewProfileMapperJobModal's Create calls
 * `onCreated` (reset to page 1 + a fresh load()) instead of navigating
 * away, so a newly created job shows up right here in the table - see
 * its own header comment.
 *
 * Below the header, `.profile-mapper-layout` splits into a wider main
 * column (the card above, unchanged) and a narrower
 * `.profile-mapper-side` column holding one vertical card - empty
 * placeholder for now, no content wired up yet. New classes rather than
 * reusing ProfileMapperJob.jsx's `.job-layout*` - those now carry a fixed
 * 640px height sized for that page's own content, which doesn't apply
 * here; this layout just stretches both columns to match each other
 * naturally (`align-items: stretch`), same as `.job-layout` did before
 * that fixed height was added.
 *
 * Run / View Results: a draft job (built but never started - see
 * NewProfileMapperJobModal.jsx) gets a ▶ Run button that calls POST
 * /api/job/{id}/start (startJob); a job that's actually "done" gets a View
 * Results button that routes to /profile-mapper/:jobId. Both are disabled
 * outside their one applicable status rather than surfacing a backend error
 * for a state the UI can just prevent - the one case that *does* reach the
 * backend (a draft with no table/file configured yet) comes back as a 400
 * whose message gets reworded into something a non-engineer can act on
 * (friendlyStartError below) and shown as an error toast.
 *
 * Paging, debounced search, filtering, sorting, the fetch itself, and the
 * silent poll that keeps active rows moving all live in useJobList - this page
 * and Validator.jsx ran identical copies of that logic, differing only in the
 * step they query and one toast message, so every fix had to be made twice.
 * See hooks/useJobList.js for the polling and toast-on-completion mechanics.
 */
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
import { DATABASE_TYPE_OPTIONS, SOURCE_TYPES, SOURCE_LABELS } from "../constants/sourceTypes.js";
import { cancelJob, deleteJob, startJob } from "../api/api.js";
import { IconError } from "../components/Icons.jsx";
import { derivePercent } from "../utils/jobProgress.js";
import { friendlyStartError } from "../utils/helpers.js";
import { STATUS_PROGRESS_COLOR, ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { useJobList } from "../hooks/useJobList.js";
import { useToast } from "../hooks/useToast.js";

const DB_TYPE_LABELS = Object.fromEntries(DATABASE_TYPE_OPTIONS.map((o) => [o.value, o.label]));

/** "Type" column: "Flat File" for flat-file jobs, else the resolved database type's label. */
function jobTypeLabel(job) {
  if (job.sourceType === SOURCE_TYPES.FLAT_FILE || job.sourceType === "csv") return SOURCE_LABELS[SOURCE_TYPES.FLAT_FILE];
  return DB_TYPE_LABELS[job.databaseType] || job.databaseType || "-";
}

export default function ProfileMapper() {
  const meta = PAGE_META["profile-mapper"];
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [newJobOpen, setNewJobOpen] = useState(false);
  const [busyId, setBusyId] = useState(null);
  /* Phase 5: ConfirmDialog state instead of window.confirm */
  const [confirmState, setConfirmState] = useState(null);

  // Paging, debounced search, filtering, sorting, the fetch and the silent poll
  // all live in useJobList - shared verbatim with Validator.jsx, which runs the
  // same list against step 3.
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
          {/* Same toolbar class and control order as every other jobs list:
                search, then filters, then the primary action on the right. */}
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
                <option value={SOURCE_TYPES.FLAT_FILE}>{SOURCE_LABELS[SOURCE_TYPES.FLAT_FILE]}</option>
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
            {/* Refresh and the primary action form one right-aligned group.
                .jobs-toolbar-action's margin-left:auto only moves that button,
                so a sibling placed before it would stay packed against the
                filters instead of sitting beside it. */}
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

          {/* Jobs table */}
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
                                  {/* The reason is one click away rather than one
                                      page away - see JobErrorButton for why it is
                                      fetched on demand. */}
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
                                  {/* Icon-only, like its three neighbours. As a text button this
                                      was single-handedly the widest thing in the row, and the
                                      Actions column is the one column whose content is fixed -
                                      width spent here is width taken from Name and Description,
                                      which are not. The label lives on in title/aria-label. */}
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

      {/* Phase 5: ConfirmDialog replaces window.confirm for destructive job delete */}
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
