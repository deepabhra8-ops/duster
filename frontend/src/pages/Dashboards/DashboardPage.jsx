import { RefreshCw } from "lucide-react";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { DASHBOARD_SECTION_TABS } from "./sectionTabs.js";
import {
  Alert,
  Button,
  DimensionTile,
  FilterBar,
  RankingPanel,
  CdeList,
  TrendChart,
  Panel,
  StatusDot,
  Table,
  TableEmpty,
  TypeChip,
  Pill,
} from "../../design-system/components/index.js";
import { useDimensionsSummary } from "../../hooks/useDimensionsSummary.js";
import { useDashboardSummary } from "../../hooks/useDashboardSummary.js";
import { useConnectionsList } from "../../hooks/useConnectionsList.js";
import { useHealthCheck } from "../../hooks/useHealthCheck.js";
import { jobStartedLabel, jobStatusText, jobStatusTone, jobTypeLabel } from "./formatters.js";
import "./DashboardPage.css";

const FILTER_CHIPS = [
  { label: "Time range", value: "Last 7 days", isSet: true },
  { label: "Environment", value: "Production" },
  { label: "Segment", value: "All teams" },
];

export default function DashboardPage() {
  const healthy = useHealthCheck();
  const { data: dims, loading: dimsLoading } = useDimensionsSummary();
  const { data: summary, loading: summaryLoading } = useDashboardSummary();
  const { data: connections } = useConnectionsList();

  const connectionCount = connections?.length ?? 0;

  return (
    <>
      <SectionTabs
        items={DASHBOARD_SECTION_TABS}
        right={dims ? <span>{dims.scoringCadenceLabel}</span> : null}
      />

      <div className="dimensions-page">
        {!healthy ? (
          <Alert tone="danger" title="Backend API not running">
            Start it with <code className="ds-mono">python backend/app.py</code>, then refresh this page.
          </Alert>
        ) : null}

        <div className="dimensions-header">
          <div>
            <h1 className="dimensions-title">Dashboard</h1>
            <div className="dimensions-subtitle">
              Data health across the five core quality dimensions, scored nightly across all {connectionCount || "—"} connection
              {connectionCount === 1 ? "" : "s"}
            </div>
          </div>
          <div className="dimensions-actions">
            <Button register="secondary">Export report</Button>
            <Button register="primary">Configure thresholds</Button>
          </div>
        </div>

        <FilterBar chips={FILTER_CHIPS} />

        {dimsLoading ? (
          <p className="dimensions-muted">Loading dimension scores&hellip;</p>
        ) : (
          <div className="dimensions-tiles">
            {dims?.dimensions.map((dim) => (
              <DimensionTile key={dim.id} to="/dashboards/data-sources" {...dim} />
            ))}
          </div>
        )}

        <div className="dimensions-body">
          <div className="dimensions-col">
            <Panel
              title="Lowest scoring sources — Timeliness"
              headerAction={
                <Button register="ghost" size="xs" to="/dashboards/data-sources">
                  Drill into Data sources
                </Button>
              }
            >
              {dims ? <RankingPanel rows={dims.lowestScoringSources.map((r) => ({ ...r, href: "/dashboards/data-sources" }))} /> : null}
            </Panel>

            <Panel
              title="Critical data elements below threshold"
              headerAction={<Button register="ghost" size="xs">View all CDEs</Button>}
            >
              {dims ? <CdeList elements={dims.criticalElements.map((e) => ({ ...e, href: "/dashboards/data-sources" }))} /> : null}
            </Panel>

            <Panel title="Recent activity" flush>
              <Table>
                <thead>
                  <tr>
                    <th></th>
                    <th>Job</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Started</th>
                  </tr>
                </thead>
                {summaryLoading ? (
                  <TableEmpty colSpan={5}>Loading recent activity&hellip;</TableEmpty>
                ) : summary?.recentJobs?.length ? (
                  <tbody>
                    {summary.recentJobs.map((job) => (
                      <tr key={job.job_id}>
                        <td>
                          <StatusDot tone={jobStatusTone(job.status)} />
                        </td>
                        <td className="mono">{job.name || job.job_id}</td>
                        <td>
                          <TypeChip>{jobTypeLabel(job.step)}</TypeChip>
                        </td>
                        <td>
                          <Pill tone={jobStatusTone(job.status)}>{jobStatusText(job.status)}</Pill>
                        </td>
                        <td className="mono" style={{ color: "var(--ink-muted)" }}>
                          {jobStartedLabel(job.started)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                ) : (
                  <TableEmpty colSpan={5}>No jobs run yet.</TableEmpty>
                )}
              </Table>
            </Panel>
          </div>

          <div className="dimensions-col">
            <Panel title="Composite trend — 12 weeks">
              {dims ? <TrendChart {...dims.compositeTrend} /> : null}
            </Panel>

            <Panel title="Business impact" headerAction={<Button register="ghost" size="xs">View business goals</Button>}>
              {dims ? (
                <>
                  <div className="impact-headline">{dims.businessImpact.totalAtRisk}</div>
                  <div className="impact-caption">{dims.businessImpact.caption}</div>
                </>
              ) : null}
            </Panel>
            {dims ? (
              <Panel flush>
                {dims.businessImpact.goals.map((goal) => (
                  <div className="goal-row" key={goal.id}>
                    <div className="goal-text">
                      <div className="goal-name">{goal.name}</div>
                      <div className="goal-sub">{goal.sub}</div>
                    </div>
                    <div className="goal-value">{goal.value}</div>
                  </div>
                ))}
              </Panel>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
