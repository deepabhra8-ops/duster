/**
 * Validator.jsx - DQ Validator landing page.
 *
 * Rows are real now - GET /api/jobs?step=3 (JobRepository/JobService), the
 * same server-side pagination/search/status-filter/sort/active-polling
 * pattern ProfileMapper.jsx already uses for its own (step=1) jobs table;
 * see that file's header comment for the debounced-search / silent-poll
 * mechanics ported here verbatim. Was MOCK_JOBS (frontend-only design pass)
 * until NewValidatorJobModal.jsx's Create started producing real jobs (see
 * that file's own header comment) - a mock array could never reflect one.
 *
 * canRun/canCancel/canDelete now match the real backend guards exactly (see
 * JobService.start_draft_job/cancel_job/delete_job) rather than the old
 * mock's assumptions: Run only for "draft" (start_draft_job rejects anything
 * else with "Job is not a draft" - error/cancelled jobs can't be re-run from
 * here the way the old mock assumed), Delete for anything except
 * queued/running/cancelling (ACTIVE_STATUSES, jobStatus.js) - the old mock
 * only allowed done/cancelled, which would've wrongly blocked deleting a
 * draft or an error'd job. Run/Cancel/Delete call the real
 * startJob/cancelJob/deleteJob (api.js) with toast feedback + a reload,
 * same as ProfileMapper.jsx's handleRun/handleCancel/handleDelete.
 *
 * The status pill and the filter dropdown both display `j.status` through
 * jobStatusLabel() (helpers.js - shared with ProfileMapper.jsx's own jobs
 * table) rather than the raw value, e.g. "running" reads "In-Progress".
 * STATUS_PILL/ACTIVE_STATUSES come from constants/jobStatus.js - the same
 * status vocabulary ProfileMapper.jsx's table uses, since both are jobs off
 * the same backend now (draft/queued/running/cancelling/done/error/cancelled
 * - no more "paused", which only ever existed in the old mock data).
 *
 * The Progress column is the same ProgressBar/derivePercent/
 * STATUS_PROGRESS_COLOR wiring ProfileMapper.jsx's table already uses -
 * job.progress ({current, total}, one tick per table finished - see
 * pipeline_service.py) comes back from the same GET /api/jobs response,
 * unconditionally on job status, so it needs no extra fetch here. The
 * silent re-poll effect below (already present for the status-transition
 * toasts) is what makes a running row's bar advance without a manual
 * refresh; derivePercent clamps at 99% until status flips to "done".
 *
 * View Results and the Job ID column both land on the job details page now
 * (/validator/:jobId, ValidatorJob.jsx) - that page fetches the real job
 * itself (GET /api/job/{id}) rather than needing anything passed via router
 * state, so both entry points converge on the same fully-wired page: real
 * job id/name/description, the four dimension score gauges, and the
 * per-dimension result tabs, all off that one job response's `summary`
 * (ValidationResultService.build_summary(), stored on the job as
 * `dq_results` - no file read at request time; see that service's own
 * header comment). Still disabled outside status "done", same as before.
 *
 * The older /results/:jobId (Results.jsx) view - which this page's Job
 * ID/View Results links stopped pointing at - has since been removed
 * entirely (route, page, and its OverallScore/DimensionScores/FindingsTable
 * components), along with the "Results" and "File Uploads" sidebar items
 * and /uploads (Uploads.jsx). /run and /run/:jobId (RunRedirect.jsx) were
 * kept, just unlinked from the sidebar - Jobs.jsx's "Log" action still
 * depends on that route.
 */
import { useEffect, useState } from "react";
import { CircleX, Play, Plus, Trash2, Eye } from "lucide-react";
import RefreshButton from "../components/RefreshButton.jsx";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import NewValidatorJobModal from "../components/validator/NewValidatorJobModal.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Pagination from "../components/Pagination.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import StatusPill from "../components/StatusPill.jsx";
import JobErrorButton from "../components/JobErrorButton.jsx";
import { PAGE_META } from "../constants/appConfig.js";
import { STATUS_PROGRESS_COLOR, ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { DATABASE_TYPE_OPTIONS, SOURCE_LABELS, SOURCE_TYPES } from "../constants/sourceTypes.js";
import { cancelJob, deleteJob, startJob } from "../api/api.js";
import { IconError } from "../components/Icons.jsx";
import { derivePercent } from "../utils/jobProgress.js";
import { friendlyStartError } from "../utils/helpers.js";
import { useJobList } from "../hooks/useJobList.js";
import { useToast } from "../hooks/useToast.js";

const DB_TYPE_LABELS = Object.fromEntries(DATABASE_TYPE_OPTIONS.map((option) => [option.value, option.label]));

function jobTypeLabel(job) {
  if (job.sourceType === SOURCE_TYPES.FLAT_FILE || job.sourceType === "csv") {
    return SOURCE_LABELS[SOURCE_TYPES.FLAT_FILE];
  }
  return DB_TYPE_LABELS[job.databaseType] || job.databaseType || "—";
}

export default function Validator() {
  const meta = PAGE_META.validator;
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [newJobOpen, setNewJobOpen] = useState(false);

  /* Arriving from a Profile Mapper job's results page (?sourceJobId=...) opens
     the New Job modal with that job already chosen. The param is cleared once
     consumed so a later refresh does not reopen the modal. */
  const [searchParams, setSearchParams] = useSearchParams();
  const sourceJobId = searchParams.get("sourceJobId") || "";

  useEffect(() => {
    if (!sourceJobId) return;
    setNewJobOpen(true);
  }, [sourceJobId]);

  function closeNewJob() {
    setNewJobOpen(false);
    if (sourceJobId) {
      searchParams.delete("sourceJobId");
      setSearchParams(searchParams, { replace: true });
    }
  }
  const [busyId, setBusyId] = useState(null);
  /* Phase 5: ConfirmDialog state instead of window.confirm */
  const [confirmState, setConfirmState] = useState(null);

  // Paging, debounced search, filtering, sorting, the fetch and the silent poll
  // all live in useJobList - shared verbatim with ProfileMapper.jsx, which runs
  // the same list against step 1.
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
    step: "3",
    doneMessage: "completed successfully. Click View Results to see the DQ report.",
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
    navigate(`/validator/${jobId}`);
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

      {/* Top section: actions + filters. */}
      <div className="card page-fill">
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

        {/* One card holds the toolbar and the table, matching ProfileMapper -
            a second card put a visible gap between a filter and the rows it
            filters, which read as two unrelated panels. */}
        {state.error ? (
          <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> {state.error}</div>
        ) : (
          <>
            <div className="table-scroll jobs-table-scroll">
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
                          : 'No jobs yet. Click "New Job" to create one.'}
                      </td>
                    </tr>
                  ) : (
                    state.jobs.map((j) => {
                      const canRun = j.status === "draft";
                      const canCancel = j.status === "queued" || j.status === "running";
                      const canDelete = !ACTIVE_STATUSES.includes(j.status);
                      const canViewResults = j.status === "done";
                      return (
                        <tr key={j.job_id}>
                          <td className="job-id-cell" data-label="Job ID">
                            <Link to={`/validator/${j.job_id}`} className="mono link" title={j.job_id}>
                              {j.job_id}
                            </Link>
                          </td>
                          <td className="job-name-cell" data-label="Name" title={j.name || ""}>{j.name}</td>
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
                                <JobErrorButton jobId={j.job_id} jobName={j.name} />
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

      <NewValidatorJobModal
        open={newJobOpen}
        initialSourceJobId={sourceJobId}
        onClose={closeNewJob}
        onCreated={() => {
          closeNewJob();
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
