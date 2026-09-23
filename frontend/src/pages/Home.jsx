/**
 * Home.jsx - Post-login landing page ("Dashboard" in the sidebar - the nav
 * label was changed from "Home" to "Dashboard" in appConfig.js; the route id
 * itself stays "home" so /home, DEFAULT_ROUTE, etc. are untouched).
 *
 * Keeps the wireframe's grid shape (a row of small tiles, a large panel below,
 * and a side rail) but bound to GET /api/dashboard/summary rather than the
 * static placeholders this page originally shipped with.
 */
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

/** A DQ score is stored 0..1; the dashboard shows it as a percentage. */
function formatScore(score) {
  if (score === null || score === undefined) return "-";
  return `${(Number(score) * 100).toFixed(1)}%`;
}

/* Names are cut to whatever the Name column can show, by CSS rather than by a
   character count, with the full name on hover.

   A fixed cut was tried first and is the wrong tool: at 10 characters every
   seeded name collapsed to "Profile - ..." / "Validation...", and raising it to
   15 only moved the problem while leaving the column - which is now the
   flexible one - two-thirds empty. Measuring against the actual column width
   shows about 40 characters at a typical dashboard size, adapts when the window
   changes, and leaves no gap between the name and Status. */

function jobHref(job) {
  return String(job.step) === "3"
    ? `/validator/${job.job_id}`
    : `/profile-mapper/${job.job_id}`;
}


export default function Home() {
  const meta = PAGE_META.home;

  const { username } = useAuth();

  // Per-user: every figure except the connection count is filtered server-side
  // by `Job.created_by == username`, so an unscoped key would show one user's
  // dashboard to the next person to sign in on this machine.
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
      {/* The control belongs next to the title it refreshes, not pinned to the
          far edge of the page - at full width those are a screen apart and stop
          reading as related. page-header-title makes just the heading row a
          flex line; .page-header itself is shared by 13 pages and stays as is. */}
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

      {/* Tiles span the full width, above the split. They used to sit inside
          dashboard-main, so they only ever covered the left column. */}
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

      {/* Middle row: the recent-runs list and the Jobs by Type chart side by
          side. Below it the score trend spans the full width - it is the one
          chart with a time axis, and width is what a time axis reads better
          for, where the other two are lists of a fixed number of things. */}
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
                  {/* Type and Status are fixed and narrow; Name takes whatever
                      is left. Without this the fixed layout split the width
                      three ways and truncated names that had room to spare. */}
                  {/* Status is pinned to its own width so it sits at the right
                      edge of the table. It used to be the flexible column, which
                      left a wide empty gap to the right of every status label.
                      The slack goes to Name instead - the only column whose
                      content varies - so the gap lands where a long name can
                      use it. */}
                  <colgroup>
                    <col style={{ width: "82px" }} />
                    <col />
                    <col style={{ width: "132px" }} />
                  </colgroup>
                  <thead>
                    {/* Type, Name, Status. Created By was dropped because the
                        dashboard is already scoped to the signed-in user's own
                        jobs, and Started At because at half width its timestamp
                        was the column forcing the row wider than the panel. The
                        jobs pages carry the full detail; this is a glance. */}
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
                          {/* One letter, not "Profile Mapper" - the full label
                              was the widest thing in the row for a value with
                              only two possibilities. title/aria carry the
                              meaning for anyone who needs it spelled out. */}
                          {String(job.step) === "3" ? (
                            <span className="job-type-flag is-validator" title="Validator" aria-label="Validator">V</span>
                          ) : (
                            <span className="job-type-flag is-profile-mapper" title="Profile Mapper" aria-label="Profile Mapper">P</span>
                          )}
                        </td>
                        <td className="dashboard-name-cell">
                          {/* title carries the full name on hover; the cell
                              ellipsises whatever does not fit. */}
                          <Link
                            to={jobHref(job)}
                            title={job.name || job.job_id}
                          >
                            {job.name || job.job_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td>
                          {/* The same pill the jobs tables and the Jobs by Type
                              legend use. This cell had its own inline swatch in
                              the --chart-* palette, so one status wore three
                              different looks across the app - and here it was
                              the only one with no icon, which is what a reader
                              needs when the colour is a 10px square. */}
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

      {/* Full width, below the split. */}
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
