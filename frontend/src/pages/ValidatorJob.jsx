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

function DimensionScoreCard({ label, score, stats, notRunCount = 0, loading, index = 0 }) {
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
  const createdBy = job?.created_by || "-";
  const createdAt = fmtDate(job?.started);
  const isActive = ACTIVE_STATUSES.includes(job?.status);

  const [activeSheet, setActiveSheet] = useState("All Findings");

  const { options: connectionOptions } = useSavedConnections(Boolean(job?.connection_id));
  const connectionLabel = useMemo(() => {
    if (!job?.connection_id) return "";
    return connectionOptions.find((o) => o.value === job.connection_id)?.label || "";
  }, [connectionOptions, job?.connection_id]);

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

  const loading = state.loading;
  const notRunCount = summary.not_run_count || 0;
  const dimensionScore = (label) =>
    label === "Overall Score" ? summary.overall_score ?? 0 : dims[label] ?? 0;

  const allFindings = (summary.sheets || {})["All Findings"] || [];
  const rulesApplied = allFindings.length;

  const sheetFor = (label) =>
    (summary.sheets || {})[label === "Overall Score" ? "All Findings" : label] || [];

  const dimensionStats = (label) => {
    const ran = sheetFor(label).filter((row) => !isNotRunRow(row));
    return { run: ran.length, failed: ran.filter((row) => row.score < 1).length };
  };

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
              <LovUploadPanel value={job?.params?.lov_file || null} readOnly compact />
            </div>
          </div>

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
