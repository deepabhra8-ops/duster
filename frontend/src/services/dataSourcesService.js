/**
 * The five observability pillars (Freshness, Volume, Distribution, Schema changes, Lineage
 * impact) have no backend support yet — the connection model tracks credentials, not live
 * telemetry. This returns realistic sample data for whichever source is selected, so the
 * Data Sources page can be built and reviewed without fabricating numbers inside a
 * component. The *source list itself* is real (see connectionsService.listConnectionsSummary);
 * only this per-source detail is a placeholder.
 *
 * TODO: replace with a real call once a `GET /api/connections/:id/observability` endpoint
 * (or similar) exists. DataSourcesPage already reads through useSourceObservability(id).
 */
const SAMPLE_BY_SOURCE = {
  "billing-mysql": {
    freshness: {
      lastUpdatedLabel: "2h 14m",
      isOverdue: true,
      subLabel: "Expected every 30 min · overdue by 1h 44m",
      ticks: ["success", "success", "warning", "success", "success", "danger", "danger", "idle"],
    },
    volume: {
      bars: [88, 92, 85, 90, 15, 89, 91, 87, 93, 90],
      anomalyIndex: 4,
      note: "-83% vs 7-day average on Thu",
    },
    distribution: {
      shifts: [
        { label: "Null rate · account_status", before: "0.4%", after: "6.2%", beforePct: 6, afterPct: 62, tone: "danger" },
        { label: "Avg(transaction_amount)", before: "$84.20", after: "$61.10", beforePct: 84, afterPct: 61, tone: "warning" },
      ],
      caption: "2 columns shifted beyond expected range",
    },
    schemaChanges: [
      { kind: "add", text: "loyalty_tier", detail: "on customers", when: "2d ago" },
      { kind: "change", text: "signup_date: varchar → timestamp", detail: "", when: "1h ago" },
      { kind: "remove", text: "legacy_flag", detail: "on accounts", when: "5d ago" },
    ],
    lineage: {
      chain: [
        { kind: "source", label: "Source", name: "billing-mysql.accounts" },
        { kind: "source", label: "dbt model", name: "stg_accounts" },
        { kind: "source", label: "dbt model", name: "fct_billing" },
      ],
      branch: [
        { kind: "at-risk", label: "BI dashboard", name: "Executive Revenue" },
        { kind: "at-risk", label: "ML model", name: "Churn predictor" },
      ],
      affectedCount: 3,
    },
  },
};

const DEFAULT_SAMPLE = SAMPLE_BY_SOURCE["billing-mysql"];

export async function getSourceObservability(sourceName) {
  return { ok: true, data: SAMPLE_BY_SOURCE[sourceName] || DEFAULT_SAMPLE };
}

export default { getSourceObservability };
