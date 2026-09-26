/**
 * Adapter between the data-quality API (`/api/quality-rules`, see
 * backend/routes/quality_rule_routes.py) and the shapes RuleEditorPage and
 * RunResultsPage render. The backend speaks the rule model from the PySpark DQ design
 * doc: pass-rate thresholds are fractions (0.99), scores are raw fractions, and table
 * types are MANAGED/EXTERNAL/VIEW. The editor speaks percentages and toggles, so every
 * conversion between the two lives here, and nowhere in a component.
 */
import {
  cancelQualityRun,
  dryRunQualityRules,
  duplicateQualityRule,
  fetchQualityRun,
  fetchQualityRunResults,
  listQualityRules,
  listQualityRuns,
  qualityRunResultsCsvUrl,
  setQualityRuleEnabled,
  startQualityRun,
  updateQualityRule,
} from "../api/api.js";

const DIMENSION_ORDER = ["completeness", "validity", "uniqueness", "timeliness", "consistency", "accuracy"];

const UNIT_BY_TEMPLATE = { unique_ratio: "ratio", freshness_hours: "hours", row_count: "rows" };

const OP_SYMBOL = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=" };

const STATUS_BREAKDOWN_LABELS = [
  { status: "PASS", tone: "success", label: "Met its threshold" },
  { status: "WARN", tone: "warning", label: "Missed a warn-severity threshold" },
  { status: "FAIL", tone: "danger", label: "Missed an error-severity threshold" },
  { status: "ERROR", tone: "error", label: "Couldn't be evaluated — see message" },
  { status: "NO_DATA", tone: "neutral", label: "Table had no rows to check" },
  { status: "SKIPPED", tone: "skip", label: "Column type doesn't fit the template" },
];

const TONE_BY_STATUS = { FAIL: "danger", ERROR: "error", WARN: "warning", NO_DATA: "idle", PASS: "success", SKIPPED: "idle" };

// Shown in full in the dry-run panel before collapsing into "+ N more".
const PLAN_TABLE_ROWS = 6;
const PLAN_SKIP_ROWS = 5;
const RESULT_ROWS = 500;

function capitalize(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function round(value, digits) {
  return Number(Number(value).toFixed(digits));
}

function parseUtc(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function timeLabel(value) {
  const date = parseUtc(value);
  return date ? `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC` : "never";
}

function dateTimeLabel(value) {
  const date = parseUtc(value);
  if (!date) return "—";
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${timeLabel(value)}`;
}

function durationLabel(ms) {
  if (ms == null) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function intLabel(value) {
  return value == null ? "—" : Number(value).toLocaleString("en-US");
}

function compactLabel(value) {
  if (value == null) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${round(value / 1e9, 1)}B`;
  if (abs >= 1e6) return `${round(value / 1e6, 1)}M`;
  if (abs >= 1e3) return `${round(value / 1e3, 1)}K`;
  return String(value);
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function percent(fraction) {
  return fraction == null ? null : fraction * 100;
}

function trimNumber(value, digits = 4) {
  return String(round(value, digits));
}

// ---- rules ----

function statusToneFor(rule) {
  if (!rule.enabled || !rule.lastRun) return "idle";
  const counts = rule.lastRun.counts || {};
  if (counts.FAIL) return "danger";
  if (counts.ERROR) return "error";
  if (counts.WARN) return "warning";
  if (counts.PASS) return "success";
  return "idle";
}

function inferScopeLevel(scope) {
  const isGlob = (value) => /[*?[]/.test(value || "*");
  if (isGlob(scope.catalog)) return "all";
  if (scope.schema === "*" || !scope.schema) return "catalog";
  if (isGlob(scope.schema) || isGlob(scope.table)) return "schema";
  if (isGlob(scope.column)) return "table";
  return "column";
}

function toUiThreshold(rule) {
  const { metric, op, value } = rule.threshold;

  if (metric === "pass_rate") return { metric, op, value: round(value * 100, 4), unit: "%" };

  return { metric, op, value, unit: UNIT_BY_TEMPLATE[rule.template] || "" };
}

function toUiParams(rule) {
  const params = { ...(rule.params || {}) };

  if (rule.template === "allowed_values" && Array.isArray(params.values)) params.values = params.values.join(", ");
  if (rule.template === "in_range") {
    params.min = params.min ?? "";
    params.max = params.max ?? "";
  }

  return params;
}

function toUiRule(rule) {
  const tableTypes = rule.scope.tableTypes || [];
  const counts = rule.lastRun?.counts || {};

  return {
    ruleId: rule.ruleId,
    name: rule.name,
    template: rule.template,
    version: rule.version,
    enabled: rule.enabled,
    description: rule.description || "",
    params: toUiParams(rule),
    scope: {
      level: rule.scope.level || inferScopeLevel(rule.scope),
      catalog: rule.scope.catalog,
      schema: rule.scope.schema,
      table: rule.scope.table,
      column: rule.scope.column,
    },
    exclude: rule.scope.exclude || [],
    tableTypes: {
      managed: tableTypes.includes("MANAGED"),
      external: tableTypes.includes("EXTERNAL"),
      view: tableTypes.includes("VIEW"),
    },
    threshold: toUiThreshold(rule),
    severity: rule.severity,
    weight: rule.weight,
    nullPolicy: rule.nullPolicy,
    rowFilter: rule.rowFilter || "",
    lastRun: {
      runId: rule.lastRun?.runId || null,
      atLabel: timeLabel(rule.lastRun?.at),
      fail: counts.FAIL || 0,
      pass: counts.PASS || 0,
      noData: counts.NO_DATA || 0,
      skipped: counts.SKIPPED || 0,
    },
  };
}

/**
 * Editor state → API payload. `draft` is the rule shape the editor holds (the same
 * shape `getRule` returns): threshold values for pass rates are percentages, table
 * types are toggles, and number inputs may still be strings.
 */
export function toRulePayload(draft) {
  const threshold = draft.threshold || {};
  const value = Number(threshold.value);
  const tableTypes = draft.tableTypes || {};
  const scope = draft.scope || {};

  const payload = {
    name: draft.name,
    description: draft.description || null,
    template: draft.template,
    params: draft.params || {},
    threshold: {
      metric: threshold.metric,
      op: threshold.op,
      value: threshold.metric === "pass_rate" ? value / 100 : value,
    },
    severity: draft.severity,
    weight: Number(draft.weight),
    nullPolicy: draft.nullPolicy,
    rowFilter: draft.rowFilter?.trim() ? draft.rowFilter : null,
    scope: {
      level: scope.level,
      catalog: scope.catalog,
      schema: scope.schema,
      table: scope.table,
      column: scope.column,
      exclude: draft.exclude || [],
      tableTypes: [
        tableTypes.managed && "MANAGED",
        tableTypes.external && "EXTERNAL",
        tableTypes.view && "VIEW",
      ].filter(Boolean),
    },
  };

  if (draft.enabled !== undefined) payload.enabled = draft.enabled;
  if (draft.version !== undefined) payload.version = draft.version;

  return payload;
}

async function fetchRules() {
  const { ok, data, error } = await listQualityRules();
  if (!ok) return { ok, error };
  return { ok: true, data: data.data };
}

export async function getRuleLibrary() {
  const { ok, data, error } = await fetchRules();
  if (!ok) return { ok, error };

  const byDimension = new Map();

  for (const rule of data.rules) {
    const key = rule.dimension || "other";
    if (!byDimension.has(key)) byDimension.set(key, []);
    byDimension.get(key).push({
      ruleId: rule.ruleId,
      name: rule.name,
      template: rule.template,
      statusTone: statusToneFor(rule),
      disabled: !rule.enabled,
    });
  }

  const rank = (dimension) => {
    const index = DIMENSION_ORDER.indexOf(dimension);
    return index === -1 ? DIMENSION_ORDER.length : index;
  };

  return {
    ok: true,
    data: {
      groups: [...byDimension.entries()]
        .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
        .map(([dimension, rules]) => ({ dimension: capitalize(dimension), rules })),
      totalRules: data.totalRules,
      failingCount: data.failingRules,
      lastRunLabel: timeLabel(data.lastRun?.completedAt),
    },
  };
}

/** The editor selects rules by name; the list endpoint already carries every field. */
export async function getRule(ruleName) {
  const { ok, data, error } = await fetchRules();
  if (!ok) return { ok, error };

  const rule = data.rules.find((r) => r.name === ruleName);
  if (!rule) return { ok: false, error: "Rule not found" };

  return { ok: true, data: toUiRule(rule) };
}

async function unwrapRule(promise) {
  const { ok, data, error } = await promise;
  if (!ok) return { ok, error };
  return { ok: true, data: toUiRule(data.data) };
}

export const saveRule = (draft) => unwrapRule(updateQualityRule(draft.ruleId, toRulePayload(draft)));

export const setRuleEnabled = (ruleId, enabled) => unwrapRule(setQualityRuleEnabled(ruleId, enabled));

export const duplicateRule = (ruleId) => unwrapRule(duplicateQualityRule(ruleId));

// ---- dry run ----

function boundColumnsLabel(table) {
  if (table.columns.length) return table.columns.join(", ");
  return table.bindingCount ? "table-level" : "no matching columns";
}

function toUiPlan(plan) {
  const tables = plan.tables || [];
  const skipped = plan.skipped || [];
  const scan = plan.scan;
  const shownTables = tables.slice(0, PLAN_TABLE_ROWS);
  const moreTables = plan.tableCount - shownTables.length;
  const moreSkips = plan.skippedCount - Math.min(skipped.length, PLAN_SKIP_ROWS);
  const problems = [...(plan.errors || []), ...(plan.bindingErrors || [])];

  return {
    tables: String(plan.tableCount),
    bindings: String(plan.bindingCount),
    skipped: String(plan.skippedCount),
    excluded: String(plan.excludedCount),
    rows: shownTables.map((t) => ({
      table: t.fqn,
      count: String(t.bindingCount),
      columns: boundColumnsLabel(t),
    })),
    moreTables: moreTables > 0 ? `+ ${plural(moreTables, "more table")}` : "",
    skips: skipped.slice(0, PLAN_SKIP_ROWS).map((s) => ({ column: s.target, reason: s.reason })),
    moreSkips: moreSkips > 0 ? `+ ${plural(moreSkips, "more column")}` : "",
    sql: scan ? scan.sql : "-- Nothing to scan: no column in scope fits this template.",
    scanOf: scan ? `Scan 1 of ${plan.scanTableCount}` : "Scan",
    runLabel: `Run on ${plural(plan.tableCount, "table")}`,
    problems: problems.map((p) => `${p.target}: ${p.message}`),
    truncated: plan.truncated,
  };
}

export async function dryRunRule(draft) {
  const { ok, data, error } = await dryRunQualityRules({ rule: toRulePayload(draft) });
  if (!ok) return { ok, error };
  return { ok: true, data: toUiPlan(data.data) };
}

// ---- runs ----

function isBlank(value) {
  return value == null || String(value).trim() === "";
}

export async function startRun({ ruleIds, where, sampleFraction, maxParallelTables, scope } = {}) {
  const body = {};
  if (ruleIds) body.ruleIds = ruleIds;
  if (scope) body.scope = scope;
  if (!isBlank(where)) body.where = where.trim();
  if (!isBlank(sampleFraction)) body.sampleFraction = Number(sampleFraction);
  if (!isBlank(maxParallelTables)) body.maxParallelTables = Number(maxParallelTables);

  const { ok, data, error } = await startQualityRun(body);
  if (!ok) return { ok, error };
  return { ok: true, data: data.data };
}

export const cancelRun = (runId) => cancelQualityRun(runId);

export const runResultsCsvUrl = (runId) => qualityRunResultsCsvUrl(runId || "latest");

export async function getRuns() {
  const { ok, data, error } = await listQualityRuns();
  if (!ok) return { ok, error };
  return {
    ok: true,
    data: data.data.items.map((run) => ({
      runId: run.runId,
      status: run.status,
      atLabel: dateTimeLabel(run.completedAt || run.createdAt),
    })),
  };
}

function formatThreshold(result) {
  const { metric, op, value } = result.threshold;
  if (value == null) return "—";
  const symbol = OP_SYMBOL[op] || op;
  if (metric === "pass_rate") return `${symbol} ${trimNumber(value * 100, 2)}%`;
  if (result.template === "freshness_hours") return `${symbol} ${trimNumber(value, 2)} h`;
  if (result.template === "unique_ratio") return `${symbol} ${Number(value).toFixed(3)}`;
  return `${symbol} ${intLabel(value)}`;
}

function formatMetric(result) {
  const value = result.metricValue;
  if (value == null) return "—";
  if (result.threshold.metric === "pass_rate") return `${(value * 100).toFixed(2)}%`;
  if (result.template === "freshness_hours") return `${value.toFixed(1)} h`;
  if (result.template === "unique_ratio") return value.toFixed(3);
  if (result.template === "row_count") return compactLabel(value);
  return trimNumber(value);
}

function toUiResult(result) {
  return {
    status: result.status,
    rule: result.ruleName,
    template: result.template,
    target: result.target || "—",
    total: intLabel(result.totalCount),
    failing: intLabel(result.failCount),
    metric: formatMetric(result),
    threshold: result.status === "SKIPPED" ? "—" : formatThreshold(result),
    message: result.message || (result.level === "table" ? "Table-level" : "—"),
  };
}

function toUiTree(nodes, depth = 0) {
  return nodes.map((node, index) => {
    const ui = {
      name: node.name,
      statusTone: TONE_BY_STATUS[node.worstStatus] || "idle",
      rowWeighted: percent(node.rowWeighted),
      simpleAvg: percent(node.simpleAverage),
      bindings: node.bindings,
      notPassing: node.notPassing,
      depth,
    };

    if (node.kind === "table") {
      if (node.worstStatus === "NO_DATA") ui.kind = "no data";
      return ui;
    }

    return {
      ...ui,
      kind: node.kind,
      // Open the worst catalog and its worst schema; children arrive worst-first.
      expanded: index === 0 && depth < 2,
      children: toUiTree(node.children || [], depth + 1),
    };
  });
}

function scoreDelta(current, previous) {
  // The design only defines a "fell since last run" marker, so rises show nothing.
  if (current == null || previous == null || current >= previous) return "";
  return trimNumber((previous - current) * 100, 2);
}

function dimensionTone(met, total) {
  const share = total ? met / total : 1;
  if (share >= 0.9) return "success";
  return share >= 0.75 ? "warning" : "danger";
}

function toUiRun(summary, results) {
  const run = summary.run;
  const kpis = summary.kpis || {};
  const previous = summary.previous?.kpis;
  const counts = summary.statusCounts || results.counts || {};
  const all = counts.ALL || 0;
  const worst = summary.worstSeverity || {};
  const metPct = kpis.thresholdsEvaluated ? (kpis.thresholdsMet / kpis.thresholdsEvaluated) * 100 : null;
  const scoreValue = (fraction) => (fraction == null ? "—" : (fraction * 100).toFixed(2));
  const sampling = run.sampleFraction ? `sampled ${trimNumber(run.sampleFraction * 100, 2)}%` : "not sampled";

  return {
    summary: {
      runId: run.runId,
      atLabel: dateTimeLabel(run.completedAt || run.createdAt),
      ruleCount: run.ruleCount,
      tableCount: run.tableCount,
      resultCount: run.resultCount,
      durationLabel: durationLabel(run.durationMs),
      scanLabel: `${run.where ? "incremental" : "full scan"} · ${sampling}`,
      failing: counts.FAIL || 0,
      warnings: counts.WARN || 0,
      ruleIds: run.ruleIds,
      scope: run.scope,
      where: run.where,
      sampleFraction: run.sampleFraction,
      maxParallelTables: run.maxParallelTables,
    },
    kpiTiles: [
      {
        label: "Row-weighted score",
        typeChip: "micro",
        value: scoreValue(kpis.rowWeighted),
        unit: "%",
        caption: "Σ passing rows ÷ Σ checked rows. Big tables dominate.",
        deltaLabel: scoreDelta(kpis.rowWeighted, previous?.rowWeighted),
      },
      {
        label: "Table average",
        typeChip: "macro",
        value: scoreValue(kpis.tableAverage),
        unit: "%",
        caption: "Mean of per-table pass rates. Every table counts once.",
        deltaLabel: scoreDelta(kpis.tableAverage, previous?.tableAverage),
      },
      {
        label: "Thresholds met",
        typeChip: "status",
        value: String(kpis.thresholdsMet ?? "—"),
        unit: ` / ${kpis.thresholdsEvaluated ?? "—"}`,
        caption: metPct == null ? "No evaluated bindings." : `${metPct.toFixed(1)}% of evaluated bindings. Skipped aren't counted.`,
        deltaLabel:
          previous && kpis.thresholdsMet < previous.thresholdsMet ? String(previous.thresholdsMet - kpis.thresholdsMet) : "",
      },
    ],
    worstSeverity: {
      severity: worst.severity || "none",
      bindingsLabel: worst.severity ? `${plural(worst.bindings, "binding")} · ${plural(worst.rules, "rule")}` : "Nothing failing",
      caption: worst.errors ? `Plus ${plural(worst.errors, "binding")} that couldn't be evaluated.` : "Every binding was evaluated.",
    },
    rollupTree: toUiTree(summary.tree || []),
    statusBreakdown: STATUS_BREAKDOWN_LABELS.map((entry) => ({
      ...entry,
      count: counts[entry.status] || 0,
      pct: all ? round(((counts[entry.status] || 0) / all) * 100, 1) : 0,
    })),
    dimensionThresholds: (summary.dimensions || []).map((d) => ({
      dimension: capitalize(d.dimension),
      met: d.met,
      total: d.total,
      tone: dimensionTone(d.met, d.total),
    })),
    resultRows: results.items.map(toUiResult),
    resultTotals: counts,
  };
}

/** Defaults to the latest finished run. */
export async function getRunResults(runId = "latest") {
  const [summary, results] = await Promise.all([
    fetchQualityRun(runId),
    fetchQualityRunResults(runId, { status: "ALL", pageSize: RESULT_ROWS }),
  ]);

  if (!summary.ok) return { ok: false, error: summary.error };
  if (!results.ok) return { ok: false, error: results.error };

  return { ok: true, data: toUiRun(summary.data.data, results.data.data) };
}
