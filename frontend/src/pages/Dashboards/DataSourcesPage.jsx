import { useEffect, useState } from "react";
import { Activity, ArrowRight, ChartColumn, Clock, Columns3, Network } from "lucide-react";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { DASHBOARD_SECTION_TABS } from "./sectionTabs.js";
import { Breadcrumb, Button, ComponentFilter, FilterBar, Pill, PillarCard, SourceList } from "../../design-system/components/index.js";
import { useConnectionsList } from "../../hooks/useConnectionsList.js";
import { useSourceObservability } from "../../hooks/useSourceObservability.js";
import "./DataSourcesPage.css";

const FILTER_CHIPS = [
  { label: "Time range", value: "Last 7 days", isSet: true },
  { label: "Environment", value: "Production" },
  { label: "Segment", value: "All teams" },
];

const REVIEW_PILL_BY_TONE = {
  danger: { tone: "danger", label: "Needs attention" },
  warning: { tone: "warning", label: "Needs review" },
};

const DIFF_MARK = { add: { symbol: "+", color: "var(--success)" }, change: { symbol: "~", color: "var(--warning)" }, remove: { symbol: "−", color: "var(--danger)" } };

/**
 * Only used when `mock` is true (the /dev/data-sources-preview route). Real usage never
 * fabricates connection status/score — see connectionsService.js — but a dev preview that
 * exists specifically to look at this page without a live backend is allowed to show the
 * full visual range rather than an all-idle list.
 */
const MOCK_SOURCES = [
  { id: "prod-postgres", name: "prod-postgres", statusTone: "success", score: 96 },
  { id: "analytics-snowflake", name: "analytics-snowflake", statusTone: "success", score: 94 },
  { id: "raw-events-bucket", name: "raw-events-bucket", statusTone: "danger", score: undefined },
  { id: "billing-mysql", name: "billing-mysql", statusTone: "warning", score: 78 },
  { id: "marketing-bigquery", name: "marketing-bigquery", statusTone: "syncing", score: undefined },
  { id: "warehouse-redshift", name: "warehouse-redshift", statusTone: "success", score: 91 },
  { id: "support-mongo", name: "support-mongo", statusTone: "success", score: 88 },
];

export default function DataSourcesPage({ mock = false }) {
  const real = useConnectionsList();
  const connections = mock ? MOCK_SOURCES : real.data;
  const connectionsLoading = mock ? false : real.loading;

  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    if (!selectedId && connections?.length) setSelectedId(mock ? "billing-mysql" : connections[0].id);
  }, [connections, selectedId, mock]);

  const selected = connections?.find((c) => c.id === selectedId);
  const { data: obs, loading: obsLoading } = useSourceObservability(selected?.name);

  const sources = mock
    ? MOCK_SOURCES
    : (connections || []).map((c) => ({ id: c.id, name: c.name, statusTone: "idle", score: undefined }));

  const needsAttention = sources.filter((s) => s.statusTone === "danger").length;
  const reviewPill = selected ? REVIEW_PILL_BY_TONE[selected.statusTone] : null;

  return (
    <>
      <SectionTabs
        items={DASHBOARD_SECTION_TABS}
        right={
          <span>
            {sources.length} connections{needsAttention ? ` · ${needsAttention} needs attention` : ""}
          </span>
        }
      />

      <div className="data-sources-page">
        <FilterBar chips={FILTER_CHIPS} />

        <div className="data-sources-body">
          <div className="panel data-sources-list">
            <div className="panel-header">
              <div className="panel-title-group">
                <span className="panel-title">Sources</span>
                <ComponentFilter>All statuses</ComponentFilter>
              </div>
            </div>
            {connectionsLoading ? (
              <p className="dimensions-muted" style={{ padding: "var(--space-4)" }}>
                Loading connections&hellip;
              </p>
            ) : sources.length ? (
              <SourceList sources={sources} selectedId={selectedId} onSelect={setSelectedId} />
            ) : (
              <p className="dimensions-muted" style={{ padding: "var(--space-4)" }}>
                No connections yet.
              </p>
            )}
          </div>

          <div className="data-sources-detail">
            {selected ? (
              <div className="data-sources-detail-head">
                <Breadcrumb segments={[{ label: "Data sources", href: "/dashboards/data-sources" }, { label: selected.name }]} />
                {reviewPill ? (
                  <Pill tone={reviewPill.tone} className="data-sources-review-pill">
                    {reviewPill.label}
                  </Pill>
                ) : null}
                <div className="data-sources-detail-actions">
                  <Button register="secondary" size="xs">
                    View lineage graph
                  </Button>
                  <Button register="primary" size="xs">
                    Acknowledge
                  </Button>
                </div>
              </div>
            ) : null}

            <DetailBody
              selected={selected}
              connectionsLoading={connectionsLoading}
              obsLoading={obsLoading}
              obs={obs}
            />
          </div>
        </div>
      </div>
    </>
  );
}

function DetailBody({ selected, connectionsLoading, obsLoading, obs }) {
  if (!selected) {
    if (connectionsLoading) return null;
    return <p className="dimensions-muted">Add a connection to see its data quality signals here.</p>;
  }

  if (obsLoading || !obs) {
    return <p className="dimensions-muted">Loading observability data&hellip;</p>;
  }

  return (
    <>
      <div className="pillar-grid">
        <PillarCard
          icon={<Clock aria-hidden="true" />}
          title="Freshness"
          action={<Button register="ghost" size="xs">View history</Button>}
        >
          <div>
            <span className="freshness-stat" style={{ color: obs.freshness.isOverdue ? "var(--danger)" : "var(--success)" }}>
              {obs.freshness.lastUpdatedLabel}
            </span>
            <span style={{ fontSize: 12, color: "var(--ink-muted)" }}> since last update</span>
          </div>
          <div className="freshness-sub" style={{ color: obs.freshness.isOverdue ? "var(--danger)" : "var(--ink-muted)" }}>
            {obs.freshness.subLabel}
          </div>
          <div className="tick-row">
            {obs.freshness.ticks.map((tone, i) => (
              <span
                key={`${tone}-${i}`}
                className="tick"
                style={{ background: `var(--${tone === "idle" ? "ink-faint" : tone})`, opacity: tone === "idle" ? 0.4 : 1 }}
              />
            ))}
          </div>
          <div className="tick-caption">Last {obs.freshness.ticks.length} scheduled syncs</div>
        </PillarCard>

        <PillarCard
          icon={<ChartColumn aria-hidden="true" />}
          title="Volume"
          action={
            <>
              <ComponentFilter title="Overrides the dashboard's 7-day filter for this chart only">10 days</ComponentFilter>
              <Button register="ghost" size="xs" style={{ marginLeft: "auto" }}>
                View history
              </Button>
            </>
          }
        >
          <div className="vol-chart">
            {obs.volume.bars.map((h, i) => (
              <div key={i} className={`vol-bar${i === obs.volume.anomalyIndex ? " is-anomaly" : ""}`} style={{ height: `${h}%` }} />
            ))}
          </div>
          <div className="vol-note">
            <Pill tone="danger">Volume drop</Pill>
            <span style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>{obs.volume.note}</span>
          </div>
        </PillarCard>

        <PillarCard
          icon={<Activity aria-hidden="true" />}
          title="Distribution"
          action={<Button register="ghost" size="xs">View history</Button>}
        >
          {obs.distribution.shifts.map((shift) => (
            <div className="shift-row" key={shift.label}>
              <div className="shift-label">
                <span>{shift.label}</span>
                <span style={{ fontFamily: "var(--font-mono)", color: `var(--${shift.tone})` }}>
                  {shift.before} → {shift.after}
                </span>
              </div>
              <div className="shift-track">
                <div className="shift-before" style={{ width: `${shift.beforePct}%` }} />
                <div className="shift-after" style={{ width: `${shift.afterPct}%`, background: `var(--${shift.tone})` }} />
              </div>
            </div>
          ))}
          <div style={{ fontSize: 11, color: "var(--ink-faint)" }}>{obs.distribution.caption}</div>
        </PillarCard>

        <PillarCard
          icon={<Columns3 aria-hidden="true" />}
          title="Schema changes"
          action={<Button register="ghost" size="xs">View diff</Button>}
        >
          {obs.schemaChanges.map((change, i) => {
            const mark = DIFF_MARK[change.kind];
            return (
              <div className="diff-row" key={i}>
                <span className="diff-mark" style={{ color: mark.color }}>
                  {mark.symbol}
                </span>
                <span className="diff-text">
                  {change.text} {change.detail ? <span style={{ color: "var(--ink-faint)" }}>{change.detail}</span> : null}
                </span>
                <span className="diff-time">{change.when}</span>
              </div>
            );
          })}
        </PillarCard>
      </div>

      <PillarCard
        icon={<Network aria-hidden="true" />}
        title="Lineage impact"
        action={<Button register="ghost" size="xs">View full lineage graph</Button>}
        flex
      >
        <div className="lineage-row">
          {obs.lineage.chain.map((node, i) => (
            <span key={node.name} style={{ display: "contents" }}>
              {i > 0 ? <ArrowRight className="lin-arrow" size={16} aria-hidden="true" /> : null}
              <LineageNode node={node} />
            </span>
          ))}
          <ArrowRight className="lin-arrow" size={16} aria-hidden="true" />
          <div className="lin-branch">
            {obs.lineage.branch.map((node) => (
              <LineageNode key={node.name} node={node} />
            ))}
          </div>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>
          <strong style={{ color: "var(--danger)" }}>{obs.lineage.affectedCount} downstream assets</strong> affected by this anomaly,
          traced from the source column outward.
        </div>
      </PillarCard>
    </>
  );
}

function LineageNode({ node }) {
  return (
    <div className={`lin-node${node.kind === "source" ? " is-source" : ""}${node.kind === "at-risk" ? " is-at-risk" : ""}`}>
      <div className="lin-label">{node.label}</div>
      <div className="lin-name">{node.name}</div>
    </div>
  );
}
