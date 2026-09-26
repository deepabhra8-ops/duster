/**
 * The backend has no endpoint for per-dimension scores, source rankings, critical data
 * elements, lineage, or business-impact figures today — it only tracks an overall score
 * per job (see dashboard_service.build_summary). This service returns realistic sample
 * data shaped like the eventual response, so the Dimensions page can be built and reviewed
 * now without fabricating numbers inside a component.
 *
 * TODO: replace with a real call once a `GET /api/dashboard/dimensions` endpoint exists.
 * When it does, this is the only file that needs to change — DashboardPage already reads
 * through useDimensionsSummary().
 */
export async function getDimensionsSummary() {
  return {
    ok: true,
    data: {
      scoringCadenceLabel: "Scored nightly · last run 6h ago",
      dimensions: [
        { id: "completeness", label: "Completeness", score: 97, deltaLabel: "1.2", deltaDirection: "up", trend: [88, 89, 90, 92, 93, 95, 96, 96, 97, 97, 97, 97] },
        { id: "accuracy", label: "Accuracy", score: 91, deltaLabel: "2.1", deltaDirection: "down", trend: [95, 95, 94, 94, 93, 93, 92, 92, 91, 91, 91, 91] },
        { id: "timeliness", label: "Timeliness", score: 84, deltaLabel: "6.4", deltaDirection: "down", trend: [96, 95, 93, 91, 90, 89, 88, 87, 86, 85, 84, 84] },
        { id: "consistency", label: "Consistency", score: 88, deltaLabel: "3.0", deltaDirection: "up", trend: [80, 81, 80, 82, 83, 84, 85, 86, 86, 87, 88, 88] },
        { id: "uniqueness", label: "Uniqueness", score: 99, deltaLabel: "0.4", deltaDirection: "up", trend: [97, 97, 98, 98, 98, 98, 99, 99, 99, 99, 99, 99] },
      ],
      lowestScoringSources: [
        { id: "raw-events-bucket", name: "raw-events-bucket", score: 38, deltaLabel: "15", deltaDirection: "down" },
        { id: "billing-mysql", name: "billing-mysql", score: 61, deltaLabel: "9", deltaDirection: "down" },
        { id: "marketing-bigquery", name: "marketing-bigquery", score: 72, deltaLabel: "4", deltaDirection: "down" },
        { id: "support-mongo", name: "support-mongo", score: 85, deltaLabel: "2", deltaDirection: "up" },
        { id: "prod-postgres", name: "prod-postgres", score: 94, deltaLabel: "1", deltaDirection: "up" },
      ],
      criticalElements: [
        {
          id: "customers-ssn",
          name: "customers.ssn",
          source: "prod-postgres",
          dimension: "Completeness",
          score: 71,
          severity: "High",
          impacts: [
            { name: "KYC Compliance", kind: "report" },
            { name: "Fraud risk model", kind: "model" },
          ],
        },
        {
          id: "accounts-balance",
          name: "accounts.balance",
          source: "billing-mysql",
          dimension: "Accuracy",
          score: 68,
          severity: "High",
          impacts: [
            { name: "Executive Revenue", kind: "dashboard" },
            { name: "Churn predictor", kind: "model" },
          ],
        },
        {
          id: "vendors-tax-id",
          name: "vendors.tax_id",
          source: "analytics-snowflake",
          dimension: "Uniqueness",
          score: 82,
          severity: "Medium",
          impacts: [{ name: "Vendor Compliance", kind: "report" }],
        },
      ],
      compositeTrend: {
        points: [93, 92, 91, 90, 88, 86, 83, 80, 82, 85, 87, 89],
        target: 90,
        anomalyIndex: 7,
        anomalyLabel: "Timeliness incident",
        startLabel: "Wk 1",
        endLabel: "Wk 12",
      },
      businessImpact: {
        totalAtRisk: "$142K",
        caption: "estimated exposure this quarter from below-threshold dimensions",
        goals: [
          { id: "revenue-reporting", name: "Revenue reporting accuracy", sub: "Blocked by Accuracy · billing-mysql", value: "$96K" },
          { id: "regulatory-q3", name: "Regulatory submission (Q3)", sub: "At risk from Timeliness · 2 sources", value: "$46K" },
        ],
      },
    },
  };
}

export default { getDimensionsSummary };
