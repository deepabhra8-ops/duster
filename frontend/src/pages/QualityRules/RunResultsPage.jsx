import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Download } from "lucide-react";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { QUALITY_RULES_SECTION_TABS } from "./sectionTabs.js";
import { Button, Pill, StatusDot, Table, TypeChip } from "../../design-system/components/index.js";
import { useRuleLibrary, useRunResults } from "../../hooks/useQualityRules.js";
import { useToast } from "../../hooks/useToast.js";
import { runResultsCsvUrl, startRun } from "../../services/qualityRulesService.js";
import "./RunResultsPage.css";

const TONE_COLOR = {
  success: "var(--success)",
  warning: "var(--warning)",
  danger: "var(--danger)",
  error: "var(--danger)",
  neutral: "var(--ink-faint)",
  skip: "var(--border-strong)",
};

const PILL_TONE_BY_STATUS = { FAIL: "danger", ERROR: "error", WARN: "warning", NO_DATA: "neutral", PASS: "success", SKIPPED: "skip" };

const FILTER_KEYS = ["attention", "FAIL", "WARN", "ERROR", "NO_DATA", "SKIPPED", "PASS", "ALL"];
const FILTER_LABELS = {
  attention: "Needs attention",
  FAIL: "Fail",
  WARN: "Warn",
  ERROR: "Error",
  NO_DATA: "No data",
  SKIPPED: "Skipped",
  PASS: "Pass",
  ALL: "All",
};

function fmtScore(value) {
  return value == null ? "—" : value.toFixed(2);
}

export default function RunResultsPage() {
  const { showToast } = useToast();
  const { data: library } = useRuleLibrary();
  const { data } = useRunResults();
  const [starting, setStarting] = useState(false);

  async function runAgain() {
    const { ruleIds, scope, where, sampleFraction, maxParallelTables } = data.summary;
    setStarting(true);
    const result = await startRun({ ruleIds, scope, where, sampleFraction, maxParallelTables });
    setStarting(false);

    if (result.ok) {
      showToast({ type: "success", title: "Run started", message: "This page shows the new results once it finishes." });
    } else {
      showToast({ type: "error", title: "Couldn't start the run", message: result.error });
    }
  }

  return (
    <>
      <SectionTabs
        items={QUALITY_RULES_SECTION_TABS}
        right={library ? <span>{library.totalRules} rules · {library.failingCount} failing · last run {library.lastRunLabel}</span> : null}
      />

      {data ? (
        <div className="run-results-page">
          <RunHead
            summary={data.summary}
            starting={starting}
            onDownload={() => window.location.assign(runResultsCsvUrl(data.summary.runId))}
            onRunAgain={runAgain}
          />

          <div className="run-results-kpis">
            {data.kpiTiles.map((tile) => (
              <KpiCard key={tile.label} tile={tile} />
            ))}
            <WorstSeverityCard worst={data.worstSeverity} />
          </div>

          <div className="run-results-grid">
            <RollupPanel tree={data.rollupTree} />
            <StatusPanel breakdown={data.statusBreakdown} dimensions={data.dimensionThresholds} resultCount={data.summary.resultCount} />
          </div>

          <ResultsPanel rows={data.resultRows} totals={data.resultTotals} />
        </div>
      ) : null}
    </>
  );
}

function RunHead({ summary, starting, onDownload, onRunAgain }) {
  return (
    <div className="run-results-head">
      <div className="run-results-head-text">
        <div className="crumb">
          <Link to="/quality-rules/runs" className="crumb-link">Runs</Link>
          <span className="crumb-sep">/</span>
          <button type="button" className="dq-run-picker" aria-haspopup="listbox" aria-label={`Choose run, current ${summary.atLabel}`}>
            {summary.atLabel}
            <ChevronDown size={11} strokeWidth={2.6} aria-hidden="true" />
          </button>
          <Pill tone="danger" style={{ marginLeft: 4 }}>{summary.failing} failing</Pill>
          <Pill tone="warning">{summary.warnings} warnings</Pill>
        </div>
        <div className="dq-run-meta">
          <span>run_id <strong>{summary.runId}</strong></span>
          <span><strong>{summary.ruleCount}</strong> rules</span>
          <span><strong>{summary.tableCount}</strong> tables</span>
          <span><strong>{summary.resultCount}</strong> results</span>
          <span><strong>{summary.durationLabel}</strong></span>
          <span>{summary.scanLabel}</span>
        </div>
      </div>
      <div className="run-results-actions">
        <Button register="secondary" size="xs" onClick={onDownload}>
          <Download size={12} strokeWidth={2.2} aria-hidden="true" />
          Download CSV
        </Button>
        <Button register="primary" size="xs" onClick={onRunAgain} disabled={starting}>Run again</Button>
      </div>
    </div>
  );
}

function KpiCard({ tile }) {
  return (
    <div className="panel dq-kpi">
      <div className="dq-kpi-top">
        <span className="kpi-label">{tile.label}</span>
        <TypeChip>{tile.typeChip}</TypeChip>
      </div>
      <span className="dq-kpi-value">
        {tile.value}
        <small>{tile.unit}</small>
      </span>
      <div className="dq-kpi-foot">
        <span className="caption">{tile.caption}</span>
        {tile.deltaLabel ? <span className="dq-delta-down">&#9660; {tile.deltaLabel}</span> : null}
      </div>
    </div>
  );
}

function WorstSeverityCard({ worst }) {
  return (
    <div className="panel dq-kpi">
      <div className="dq-kpi-top">
        <span className="kpi-label">Worst failing severity</span>
      </div>
      <div className="run-results-worst-row">
        <Pill tone="danger" className="run-results-worst-pill">{worst.severity}</Pill>
        <span className="run-results-worst-label">{worst.bindingsLabel}</span>
      </div>
      <div className="dq-kpi-foot">
        <span className="caption">{worst.caption}</span>
      </div>
    </div>
  );
}

function RollupPanel({ tree }) {
  const [collapsed, setCollapsed] = useState(() => {
    const set = new Set();
    const visit = (nodes) => {
      for (const node of nodes) {
        if (node.expanded === false) set.add(node.name);
        if (node.children) visit(node.children);
      }
    };
    visit(tree);
    return set;
  });

  function toggle(name) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function renderRows(nodes) {
    return nodes.flatMap((node) => {
      if (node.isMoreRow) {
        return [
          <tr key={node.name} className="dq-more-row">
            <td colSpan={5}>
              <div style={{ paddingLeft: node.depth * 20 + 23 }}>{node.name}</div>
            </td>
          </tr>,
        ];
      }

      // A schema/catalog row is expandable if it declares a children array at all — even an
      // empty one, since not every rollup node has its drill-down fixture data yet — while a
      // leaf table row (no `children` key) never shows a toggle.
      const isExpandable = Array.isArray(node.children);
      const hasChildRows = isExpandable && node.children.length > 0;
      const isCollapsed = collapsed.has(node.name);
      const row = (
        <tr key={node.name}>
          <td>
            <div className="dq-tree-cell" style={{ paddingLeft: node.depth * 20 }}>
              {isExpandable ? (
                <button
                  type="button"
                  className="dq-tree-toggle"
                  aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${node.name}`}
                  aria-expanded={!isCollapsed}
                  onClick={() => toggle(node.name)}
                >
                  <ChevronRight size={11} strokeWidth={2.6} style={{ transform: isCollapsed ? "none" : "rotate(90deg)" }} />
                </button>
              ) : (
                <span className="dq-tree-spacer" />
              )}
              <StatusDot tone={node.statusTone} />
              <span className="dq-tree-name">{node.name}</span>
              {node.kind ? <span className="dq-tree-kind">{node.kind}</span> : null}
            </div>
          </td>
          <td className="num">{fmtScore(node.rowWeighted)}</td>
          <td className="num">{fmtScore(node.simpleAvg)}</td>
          <td className="num">{node.bindings}</td>
          <td className="num">{node.notPassing}</td>
        </tr>
      );

      const childRows = hasChildRows && !isCollapsed ? renderRows(node.children) : [];
      return [row, ...childRows];
    });
  }

  return (
    <section className="panel run-results-rollup">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title">Rollup</span>
          <span className="caption">Computed from raw counts, never from stored averages</span>
        </div>
      </div>
      <Table>
        <thead>
          <tr>
            <th>Scope</th>
            <th className="num">Row-weighted</th>
            <th className="num">Simple avg</th>
            <th className="num">Bindings</th>
            <th className="num">Not passing</th>
          </tr>
        </thead>
        <tbody>{renderRows(tree)}</tbody>
      </Table>
    </section>
  );
}

function StatusPanel({ breakdown, dimensions, resultCount }) {
  return (
    <section className="panel run-results-status">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title">Result status</span>
          <span className="caption ds-mono">{resultCount} results</span>
        </div>
      </div>
      <div className="run-results-stack-wrap">
        <div className="dq-stack" aria-hidden="true">
          {breakdown.map((b) => (
            <span
              key={b.status}
              style={{ flex: `${b.count} 1 0`, background: TONE_COLOR[b.tone], opacity: b.tone === "error" ? 0.55 : 1 }}
            />
          ))}
        </div>
      </div>
      {breakdown.map((b) => (
        <div key={b.status} className="dq-legend-row">
          <Pill tone={b.tone} className="pill-st">{b.status}</Pill>
          <span className="dq-legend-desc">{b.label}</span>
          <span className="dq-legend-n">{b.count}</span>
          <span className="dq-legend-pct">{b.pct}%</span>
        </div>
      ))}

      <div className="dq-sub-head" style={{ marginTop: 4 }}>Thresholds met by dimension</div>
      <div style={{ paddingBottom: 10 }}>
        {dimensions.map((d) => (
          <div key={d.dimension} className="dq-dim-row">
            <span className="dq-dim-name">{d.dimension}</span>
            <div className="dq-dim-track">
              <div className="dq-dim-fill" style={{ width: `${((d.met / d.total) * 100).toFixed(0)}%`, background: TONE_COLOR[d.tone] }} />
            </div>
            <span className="dq-dim-n">{d.met} / {d.total}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultsPanel({ rows, totals }) {
  const [filter, setFilter] = useState("attention");

  const matches = rows.filter((r) => {
    if (filter === "ALL") return true;
    if (filter === "attention") return r.status !== "PASS" && r.status !== "SKIPPED";
    return r.status === filter;
  });
  const shown = matches.slice(0, 8);

  return (
    <section className="panel run-results-list">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title">Results</span>
          <span className="caption">One row per rule &times; column</span>
        </div>
        <div className="run-results-filters" role="group" aria-label="Filter results by status">
          {FILTER_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={`dq-ftab${filter === key ? " is-on" : ""}`}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {FILTER_LABELS[key]} <span className="n">{totals[key]}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="run-results-table-scroll">
        <Table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Rule</th>
              <th>Template</th>
              <th>Target</th>
              <th className="num">Checked</th>
              <th className="num">Failing</th>
              <th className="num">Metric</th>
              <th className="num">Threshold</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={`${r.rule}-${r.target}-${i}`}>
                <td><Pill tone={PILL_TONE_BY_STATUS[r.status]} className="pill-st">{r.status}</Pill></td>
                <td className="mono">{r.rule}</td>
                <td className="mono muted">{r.template}</td>
                <td className="mono" title={r.target}>{r.target}</td>
                <td className="num">{r.total}</td>
                <td className="num">{r.failing}</td>
                <td className="num">{r.metric}</td>
                <td className="num" style={{ color: "var(--ink-muted)" }}>{r.threshold}</td>
                <td className="muted" title={r.message}>{r.message}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <div className="run-results-table-foot">
        <span className="caption">
          Showing <span className="ds-mono" style={{ color: "var(--ink)" }}>{shown.length}</span> of{" "}
          <span className="ds-mono" style={{ color: "var(--ink)" }}>{totals[filter]}</span> &middot; worst first
        </span>
        <span className="caption">
          Stored in <span className="ds-mono" style={{ color: "var(--ink)" }}>main.dq.results</span> &middot; append-only
        </span>
      </div>
    </section>
  );
}
