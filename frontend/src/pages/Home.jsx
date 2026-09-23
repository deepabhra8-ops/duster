import RefreshButton from "../components/RefreshButton.jsx";
import { useAuth } from "../hooks/useAuth.js";
import { useCachedResource } from "../hooks/useCachedResource.js";
import { buildKey } from "../utils/pageCache.js";
import { Link } from "react-router-dom";

import { fetchDashboardSummary } from "../api/api.js";
import { PAGE_META } from "../constants/appConfig.js";
import { IconWarning } from "../components/Icons.jsx";
import JobStatusChart from "../components/JobStatusChart.jsx";
import StatusPill from "../components/StatusPill.jsx";
import TrendLineChart from "../components/TrendLineChart.jsx";

function formatScore(score) {
  if (score === null || score === undefined) return "-";
  return `${(Number(score) * 100).toFixed(1)}%`;
}

function jobHref(job) {
  return String(job.step) === "3"
    ? `/validator/${job.job_id}`
    : `/profile-mapper/${job.job_id}`;
}


export default function Home() {
  const meta = PAGE_META.home;

  const { username } = useAuth();

  const {
    data,
    error,
    loading,
    refreshing,
    lastUpdated,
    refresh,
  } = useCachedResource({
    key: buildKey(username, "dashboard"),
    fetcher: fetchDashboardSummary,
    select: (payload) => payload?.data || null,
  });

  const state = { loading, error: error || "", data };

  const jobs = data?.jobs || {};
  const recent = data?.recent_jobs || [];
  const trend = data?.score_trend || [];

  const tiles = [
    { label: "Total Jobs", value: jobs.total ?? 0, colorClass: "tile-blue" },
    { label: "Active Now", value: jobs.active ?? 0, colorClass: "tile-green" },
    { label: "Latest DQ Score", value: formatScore(data?.latest_score), colorClass: "tile-teal" },
    { label: "Connections", value: data?.connections ?? 0, colorClass: "tile-amber" },
  ];

  return (
    <section className="dashboard-page">
      <header className="page-header">
        <div className="page-header-title">
          <h2>{meta.title}</h2>
          <RefreshButton
            onRefresh={refresh}
            refreshing={refreshing}
            lastUpdated={lastUpdated}
            stampSide="right"
          />
        </div>
        <p>{meta.subtitle}</p>
      </header>

      {state.error && (
        <div className="alert alert-err">
          <IconWarning style={{ color: "var(--red)", verticalAlign: "text-bottom" }} /> {state.error}
        </div>
      )}

      <div className="dashboard-tiles">
        {tiles.map((tile) => (
          <div key={tile.label} className={`card tile-card ${tile.colorClass}`}>
            <div className="card-title">{tile.label}</div>
            {state.loading ? (
              <div className="skeleton skeleton-tile" aria-hidden="true" />
            ) : (
              <div className="tile-figure">{tile.value}</div>
            )}
          </div>
        ))}
      </div>

      <div className="dashboard-layout">
        <div className="dashboard-main">
          <div className="card dashboard-panel-lg">
            <div className="card-title">Recent Job Runs</div>

            {state.loading ? (
              <p className="section-desc">Loading…</p>
            ) : recent.length === 0 ? (
              <p className="section-desc">
                No jobs yet. Create a Profile Mapper job to get started.
              </p>
            ) : (
              <div className="table-scroll">
                <table className="tbl profile-map-table redesigned">
                  <colgroup>
                    <col style={{ width: "82px" }} />
                    <col />
                    <col style={{ width: "132px" }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Name</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((job) => (
                      <tr key={job.job_id}>
                        <td>
                          {String(job.step) === "3" ? (
                            <span className="job-type-flag is-validator" title="Validator" aria-label="Validator">V</span>
                          ) : (
                            <span className="job-type-flag is-profile-mapper" title="Profile Mapper" aria-label="Profile Mapper">P</span>
                          )}
                        </td>
                        <td className="dashboard-name-cell">
                          <Link
                            to={jobHref(job)}
                            title={job.name || job.job_id}
                          >
                            {job.name || job.job_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td>
                          <StatusPill status={job.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

        </div>

        <div className="dashboard-side">
          <div className="card dashboard-bar-card">
            <div className="card-title">Jobs by Type</div>
            {state.loading ? (
              <div className="skeleton-text sm skeleton" aria-hidden="true" />
            ) : (
              <JobStatusChart
                profilingData={jobs.profiling_by_status}
                validationData={jobs.validation_by_status}
              />
            )}
          </div>
        </div>
      </div>

      <div className="card dashboard-trend-card">
        <div className="card-title">DQ Score Trend</div>

        {state.loading ? (
          <p className="section-desc">Loading…</p>
        ) : trend.length === 0 ? (
          <p className="section-desc">
            No validation runs in the last 7 days.
          </p>
        ) : (
          <>
            <p className="section-desc" style={{ marginTop: '-4px', marginBottom: '24px' }}>
              DQ score over the last 7 days - {trend.length} day{trend.length === 1 ? '' : 's'} with runs.
            </p>
            <TrendLineChart points={trend} />
          </>
        )}
      </div>
    </section>
  );
}
