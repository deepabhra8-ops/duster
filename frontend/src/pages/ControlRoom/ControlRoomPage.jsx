import { Alert, Button, ConnectionCard, KpiTile, Panel, Pill, StatusDot, Table, TableEmpty, TypeChip } from "../../design-system/components/index.js";
import { useConnectionsList } from "../../hooks/useConnectionsList.js";
import { useDashboardSummary } from "../../hooks/useDashboardSummary.js";
import { useHealthCheck } from "../../hooks/useHealthCheck.js";
import { jobStartedLabel, jobStatusText, jobStatusTone, jobTypeLabel, scoreColorVar, scoreDelta } from "./formatters.js";
import "./ControlRoomPage.css";

export default function ControlRoomPage() {
  const healthy = useHealthCheck();
  const { data: summary, loading: summaryLoading } = useDashboardSummary();
  const { data: connections, loading: connectionsLoading } = useConnectionsList();

  const delta = scoreDelta(summary?.scoreTrend);

  return (
    <div className="control-room">
      {!healthy ? (
        <Alert tone="danger" title="Backend API not running">
          Start it with <code className="ds-mono">python backend/app.py</code>, then refresh this page.
        </Alert>
      ) : null}

      <div className="control-room-kpis">
        <KpiTile label="Total jobs" value={summaryLoading ? "—" : summary?.jobsTotal ?? 0} />
        <KpiTile
          label="Active jobs"
          value={summaryLoading ? "—" : summary?.jobsActive ?? 0}
          valueColor={summary?.jobsActive > 0 ? "var(--accent)" : undefined}
        />
        <KpiTile
          label="Latest score"
          value={summaryLoading || summary?.latestScore == null ? "—" : Math.round(summary.latestScore)}
          valueColor={scoreColorVar(summary?.latestScore)}
          delta={delta}
        />
        <KpiTile label="Connections" value={summaryLoading ? "—" : summary?.connectionsCount ?? 0} />
      </div>

      <div className="control-room-body">
        <Panel
          title="Connections"
          headerAction={<Button register="primary" size="xs">Add connection</Button>}
        >
          {connectionsLoading ? (
            <p className="control-room-muted">Loading connections&hellip;</p>
          ) : connections?.length ? (
            <div className="control-room-conn-grid">
              {connections.map((conn) => (
                <ConnectionCard
                  key={conn.id}
                  name={conn.name}
                  dbType={conn.dbType}
                  statusTone="idle"
                  statusLabel="Not monitored"
                />
              ))}
            </div>
          ) : (
            <p className="control-room-muted">No connections yet. Add one to start profiling data.</p>
          )}
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
    </div>
  );
}
