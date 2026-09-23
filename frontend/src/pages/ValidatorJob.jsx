/**
 * ValidatorJob.jsx - single DQ Validator job page.
 *
 * Fetches the job via GET /api/job/{jobId} (fetchJob, api.js) and, while the job
 * is still active, keeps polling it at JOB_POLL_INTERVAL - the same cadence and
 * shape ProfileMapperJob.jsx uses. Without that poll this page fetched once on
 * mount, so opening a job that was still running left "No DQ results yet" on
 * screen indefinitely, with no refresh control to recover from it.
 *
 * Reached two ways, both landing here: Validator.jsx's Job ID column link and
 * its View Results button. Job name/description/id come straight off the fetched
 * job, not router state, so a refresh or a direct link always shows the real thing.
 *
 * The first fetch renders the whole dashboard rather than replacing it with a
 * "Loading…" card: the gauge cards, the results card and the side rail are
 * static structure that never depends on the response, so blanking them out
 * only bought a full re-layout the moment the job arrived. Everything that is
 * actually unknown - job name, status pills, gauge fills, tab labels, grid
 * rows, the download file - renders as a placeholder of the same size and is
 * swapped in place (`loading` prop on DimensionScoreCard / ReportResultsTabs /
 * ReportSheetGrid / JobDownloadCard). The gauges show an indeterminate arc
 * sweeping their real track instead of a 0% fill, which would otherwise read
 * as a genuine score of zero.
 *
 * The four score gauges (Completeness/Conformity/Uniqueness/Overall) and the
 * ReportResultsTabs below read off job.summary - built by
 * engine/reporting/validation_summary.py::build_summary the moment a Glue run
 * finishes and stored in the `validation_results` table, not re-derived from any
 * file at request time. `summary.dimensions` only carries dimensions that actually
 * appeared in this job's rules: a job with no DQ8/DQ9/DQ11 rules never populates
 * "Consistency"/"Custom", which have no gauge or tab here anyway (their findings
 * still show in "All Findings" and still count toward Overall Score).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  AlignLeft,
  ChevronRight,
  Clock,
  Database,
  FileText,
  Hash,
  ListChecks,
  ShieldAlert,
  User,
} from "lucide-react";
import JobDownloadCard from "../components/profileMapper/JobDownloadCard.jsx";
import ScoreGauge from "../components/ScoreGauge.jsx";
import StatusPill from "../components/StatusPill.jsx";
import ReportResultsTabs, {
  NOT_RUN_TAB,
  isNotRunRow,
} from "../components/validator/ReportResultsTabs.jsx";
import { useSavedConnections } from "../hooks/useSavedConnections.js";
import { fetchJob, http, TRANSFER_TIMEOUT } from "../api/api.js";
import { JOB_POLL_INTERVAL } from "../constants/appConfig.js";
import { ACTIVE_STATUSES } from "../constants/jobStatus.js";
import { fmtDate, scoreStatusLabel, scorePillClass } from "../utils/helpers.js";
import { useToast } from "../hooks/useToast.js";
import { IconError } from "../components/Icons.jsx";
import LovUploadPanel from "../components/LovUploadPanel.jsx";
import "../styles/validator-results.css";

const EMPTY_SUMMARY = { overall_score: null, dimensions: {}, sheets: {} };

const DIMENSION_CARDS = ["Completeness", "Conformity", "Uniqueness", "Overall Score"];

/** One dimension's title + status pill + ScoreGauge, with the two counts that
 *  say how much the score is actually based on.
 *
 * The gauge alone was ambiguous: 100% over two checks and 100% over two hundred
 * are the same arc. `stats` puts "checks run" and "failed" beside it, both
 * derived from the same rows the tabs below render.
 *
 * `loading` keeps the card's chrome - title, pill slot, gauge track - exactly
 * where it will be once the score lands, swapping only the unknown values for
 * placeholders. `index` staggers both the placeholder shimmer and the reveal so
 * the four cards animate as a sweep across the row rather than all at once. */
function DimensionScoreCard({ label, score, stats, notRunCount = 0, loading, index = 0 }) {
  /* The gauge and these two counts measure different things, and the gap between
     them is the single most confusing part of this card: the percentage is a
     mean of each rule's PASS RATE OVER ROWS (validation_scorer.py -
     calculate_dimension_scores averages the rule scores, and the overall score
     averages the dimension scores), while "Failed" counts RULES. So 23 failed
     of 148 is not "15% bad", and the gauge will not equal 1 - failed/run. The
     tooltips say so where the question is asked rather than in a doc nobody
     opens. */
  const runTitle =
    `Rules whose check actually executed.` +
    (notRunCount ? ` Excludes ${notRunCount} that could not run.` : "");
  return (
    <div className="card vr-score-card">
      <div className="card-title">{label}</div>
      {loading ? (
        <span
          className="pill pill-skeleton skeleton"
          style={{ animationDelay: `${index * 0.12}s` }}
          aria-hidden="true"
        />
      ) : (
        <div className={`pill ${scorePillClass(score)} reveal-in`} style={{ "--reveal-i": index }}>
          {scoreStatusLabel(score)}
        </div>
      )}
      <div className="vr-score-body">
        <ScoreGauge score={loading ? 0 : score} loading={loading} />
        <dl className="vr-score-stats">
          <div className="vr-stat" title={runTitle}>
            <Database size={15} className="vr-stat-icon" aria-hidden="true" />
            <div>
              <dd>{loading ? <span className="skeleton skeleton-text sm" /> : stats.run}</dd>
              <dt>Checks run</dt>
            </div>
          </div>
          <div
            className="vr-stat is-fail"
            title="Rules with at least one failing row. The percentage is a row-level score, not this count over the one beside it."
          >
            <ShieldAlert size={15} className="vr-stat-icon" aria-hidden="true" />
            <div>
              <dd>{loading ? <span className="skeleton skeleton-text sm" /> : stats.failed}</dd>
              <dt>Failed</dt>
            </div>
          </div>
        </dl>
      </div>
    </div>
  );
}

/** One labelled row in the Run Details rail. */
function RunDetail({ icon: Icon, label, loading, children }) {
  return (
    <div className="vr-detail">
      <Icon size={15} className="vr-detail-icon" aria-hidden="true" />
      <div className="vr-detail-text">
        <dt>{label}</dt>
        <dd>{loading ? <span className="skeleton skeleton-text sm" /> : children}</dd>
      </div>
    </div>
  );
}

export default function ValidatorJob() {
  const { jobId } = useParams();
  const [state, setState] = useState({ loading: true, error: null, job: null });
  const [isDownloading, setIsDownloading] = useState(false);
  const { showToast } = useToast();

  // Held in a ref so the polling effect doesn't re-subscribe on every tick.
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    let timerId = null;

    async function tick() {
      const { ok, data, error } = await fetchJob(jobId);
      if (cancelledRef.current) return;

      if (!ok || !data?.job_id) {
        setState({ loading: false, error: error || "Cannot reach API", job: null });
        return;
      }

      setState({ loading: false, error: null, job: data });

      // Only an active job can still change; a terminal one is polled no further.
      if (ACTIVE_STATUSES.includes(data.status)) {
        timerId = setTimeout(tick, JOB_POLL_INTERVAL);
      }
    }

    setState((s) => ({ ...s, loading: true, error: null }));
    tick();

    return () => {
      cancelledRef.current = true;
      if (timerId) clearTimeout(timerId);
    };
  }, [jobId]);

  const job = state.job;
  const summary = job?.summary || EMPTY_SUMMARY;
  const dims = summary.dimensions || {};
  const hasData = summary.overall_score != null || Object.keys(dims).length > 0;
  const name = job?.name?.trim() || "Untitled Job";
  const description = job?.description?.trim() || "";
  // The jobs table has no created_at: `started_at` carries a server_default of
  // now() and the row is inserted the moment the job is created (as a draft),
  // so it IS the creation timestamp. The API exposes it as `started`.
  const createdBy = job?.created_by || "-";
  const createdAt = fmtDate(job?.started);
  const isActive = ACTIVE_STATUSES.includes(job?.status);

  /* Which tab the results card is showing. It lives here rather than inside
     ReportResultsTabs because the "View Not Run" button in the banner has to be
     able to switch it. */
  const [activeSheet, setActiveSheet] = useState("All Findings");

  /* The job carries connection_id, not the connection's name or type, and there
     is no endpoint that resolves one id. This is the list the New Job wizards
     already load, matched client-side - so Run Details can say "db (postgresql)"
     rather than a uuid. Falls back to nothing rather than showing a raw id. */
  const { options: connectionOptions } = useSavedConnections(Boolean(job?.connection_id));
  const connectionLabel = useMemo(() => {
    if (!job?.connection_id) return "";
    return connectionOptions.find((o) => o.value === job.connection_id)?.label || "";
  }, [connectionOptions, job?.connection_id]);

  // Let the user attempt to download if the job is done. If the file is missing
  // in S3 (e.g. wiped), the backend will return 404 and we show a clear error toast,
  // which is better than silently greying out the button and causing confusion.
  const canDownloadReport = job?.status === "done";
  const downloadReport = async () => {
    setIsDownloading(true);
    showToast({
      type: "info",
      title: "Downloading...",
      message: "Generating DQ Report, this might take a while...",
    });

    try {
      const res = await http.get(`/job/${jobId}/download/report`, {
        responseType: "blob",
        // Streamed out of S3 and can be large - not subject to the default cap.
        timeout: TRANSFER_TIMEOUT,
      });
      const blob = new Blob([res.data], { type: res.headers["content-type"] });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `DQ_Report_${jobId}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);

      showToast({
        type: "success",
        title: "Download complete",
        message: "DQ Report downloaded successfully.",
      });
    } catch (err) {
      console.error("Download failed:", err);
      showToast({
        type: "error",
        title: "Download failed",
        message: "There was an error generating the file.",
      });
    } finally {
      setIsDownloading(false);
    }
  };

  // The whole dashboard is rendered on the first paint, skeleton-filled: the
  // gauges, the results card and the side rail are static structure that never
  // depends on the response, so blanking them out for a centred "Loading…"
  // only cost a full re-layout once the job arrived. Only the unknown values
  // are placeholders, and they are swapped in place.
  const loading = state.loading;
  const notRunCount = summary.not_run_count || 0;
  const dimensionScore = (label) =>
    label === "Overall Score" ? summary.overall_score ?? 0 : dims[label] ?? 0;

  /* The two counts under each gauge, derived from the same rows the grid below
     renders rather than from a separate field - so a card and its tab can never
     disagree. "Checks run" excludes the ones that could not execute (they are
     what the banner is about); "Failed" counts executed checks that did not
     score a clean pass. */
  /* Every rule execution this run produced - the denominator behind all four
     gauges. Split into the two halves the banner above is about, so Run Details
     answers "how much was actually checked?" without the reader having to add
     up tab counts. */
  const allFindings = (summary.sheets || {})["All Findings"] || [];
  const rulesApplied = allFindings.length;

  const sheetFor = (label) =>
    (summary.sheets || {})[label === "Overall Score" ? "All Findings" : label] || [];

  const dimensionStats = (label) => {
    const ran = sheetFor(label).filter((row) => !isNotRunRow(row));
    return { run: ran.length, failed: ran.filter((row) => row.score < 1).length };
  };

  /** How many of this card's checks could not run - for its tooltip. */
  const dimensionNotRun = (label) => sheetFor(label).filter(isNotRunRow).length;

  return (
    <section className="vr">
      <header className="vr-header">
        <nav className="vr-crumbs" aria-label="Breadcrumb">
          <Link to="/validator">Validator</Link>
          <ChevronRight size={13} aria-hidden="true" />
          <span>Results</span>
          <ChevronRight size={13} aria-hidden="true" />
          <span className="vr-crumb-current">
            {loading ? <span className="skeleton skeleton-text sm" /> : name}
          </span>
        </nav>

        <div className="vr-header-row">
          <div className="vr-header-text">
            <h2>Validator Results</h2>
            <p>
              Summary of data quality validation for this run. Explore findings by category
              and download the detailed report.
            </p>
          </div>

          <div className="vr-header-meta">
            {loading ? (
              <span className="pill pill-skeleton skeleton" aria-hidden="true" />
            ) : (
              <StatusPill status={job?.status} />
            )}
            {/* Started only. The jobs table carries no finish timestamp and the
                job response exposes no duration, so a "Duration" here would have
                to be invented - see this file's header comment. */}
            <span className="vr-header-time">
              {loading ? <span className="skeleton skeleton-text sm" /> : `Started: ${createdAt}`}
            </span>
          </div>
        </div>
      </header>

      {state.error ? (
        <div className="card">
          <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> Cannot reach API ({state.error})</div>
        </div>
      ) : (
        /* One grid across both columns rather than two independent columns.
           Side by side, the rail's cards stacked in their own flow: Run Details
           began wherever the Download card happened to end, which is never the
           top of the results card next to it. Placing all five blocks in one
           grid ties each side card to the main section it belongs beside. */
        <div className={`vr-grid page-fill${notRunCount > 0 ? " has-banner" : ""}`}>
          {loading || hasData ? (
            <>
                <div className="vr-score-row vr-area-scores">
                  {DIMENSION_CARDS.map((label, index) => (
                    <DimensionScoreCard
                      key={label}
                      label={label}
                      score={dimensionScore(label)}
                      stats={dimensionStats(label)}
                      notRunCount={dimensionNotRun(label)}
                      loading={loading}
                      index={index}
                    />
                  ))}
                </div>

                {notRunCount > 0 && (
                  /* The scores above are computed only from checks that actually
                     ran. Without this, a run where half the configured checks
                     could not execute looks identical to one where everything
                     passed. The button is the other half of that: it puts the
                     rows one click away instead of asking the user to hunt for
                     NOT RUN badges scattered through All Findings. */
                  <div className="vr-banner vr-area-banner">
                    <AlertTriangle size={17} className="vr-banner-icon" aria-hidden="true" />
                    <span>
                      {notRunCount} {notRunCount === 1 ? "check" : "checks"} could not run and
                      {notRunCount === 1 ? " is" : " are"} excluded from these scores - look for
                      the <strong>NOT RUN</strong> rows below for the reason.
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm vr-banner-action"
                      onClick={() => setActiveSheet(NOT_RUN_TAB)}
                    >
                      View Not Run ({notRunCount})
                      <ChevronRight size={14} aria-hidden="true" />
                    </button>
                  </div>
                )}

                <div className="card job-placeholder-box-lg vr-area-results">
                  <div className="card-title">DQ Validation Results</div>
                  <ReportResultsTabs
                    tables={summary.tables || []}
                    sheets={summary.sheets}
                    loading={loading}
                    activeSheet={activeSheet}
                    onSheetChange={setActiveSheet}
                  />
                </div>
              </>
          ) : (
              <div className="card vr-area-scores">
                <div className="empty-state" style={{ padding: "32px" }}>
                  {isActive ? (
                    <>
                      <p style={{ fontSize: "18px", marginBottom: "8px" }}>Validation in progress…</p>
                      <p className="hint">
                        Scores and findings appear here automatically when the run finishes.
                      </p>
                    </>
                  ) : (
                    <>
                      <p style={{ fontSize: "18px", marginBottom: "8px" }}>No DQ results yet</p>
                      <p className="hint">Run this job to see scores and findings here.</p>
                    </>
                  )}
                </div>
              </div>
          )}

          <div className="vr-area-download">
            <JobDownloadCard
              title="Download Report"
              showDownload={canDownloadReport}
              downloadFilename={`DQ_Report_${jobId}.xlsx`}
              onDownload={downloadReport}
              isDownloading={isDownloading}
              loading={loading}
            />

          </div>

          <div className="vr-area-lov">
            <div className="card vr-lov-card">
              {/* The LOV this job was created with. Fixed once the job
                  exists, so the results always say what was actually
                  validated against. */}
              <LovUploadPanel value={job?.params?.lov_file || null} readOnly compact />
            </div>
          </div>

          {/* The questions asked of a result set being read some time after the
              run: what was it, who ran it, when, and against what. */}
          <div className="card vr-details vr-area-details">
              <div className="card-title">Run Details</div>
              <dl className="vr-detail-list">
                <RunDetail icon={FileText} label="Job Name" loading={loading}>
                  {name}
                </RunDetail>
                <RunDetail icon={Hash} label="Job ID" loading={loading}>
                  <span className="mono vr-detail-mono" title={jobId}>{jobId}</span>
                </RunDetail>
                <RunDetail icon={User} label="Started By" loading={loading}>
                  {createdBy}
                </RunDetail>
                <RunDetail icon={Clock} label="Started At" loading={loading}>
                  {createdAt}
                </RunDetail>
                {rulesApplied > 0 ? (
                  <RunDetail icon={ListChecks} label="Rules Applied" loading={loading}>
                    {rulesApplied}
                    {notRunCount > 0 ? (
                      <span className="vr-detail-sub"> · {notRunCount} could not run</span>
                    ) : null}
                  </RunDetail>
                ) : null}
                {description ? (
                  <RunDetail icon={AlignLeft} label="Description" loading={loading}>
                    {description}
                  </RunDetail>
                ) : null}
                {connectionLabel ? (
                  <RunDetail icon={Database} label="Source Connection" loading={loading}>
                    {connectionLabel}
                  </RunDetail>
                ) : null}
              </dl>
          </div>
        </div>
      )}
    </section>
  );
}
