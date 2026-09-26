import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/api.js", () => ({
  cancelQualityRun: vi.fn(),
  dryRunQualityRules: vi.fn(),
  duplicateQualityRule: vi.fn(),
  fetchQualityRun: vi.fn(),
  fetchQualityRunResults: vi.fn(),
  listQualityRules: vi.fn(),
  listQualityRuns: vi.fn(),
  qualityRunResultsCsvUrl: vi.fn((id) => `/api/quality-rules/runs/${id}/results.csv`),
  setQualityRuleEnabled: vi.fn(),
  startQualityRun: vi.fn(),
  updateQualityRule: vi.fn(),
}));

import * as api from "../api/api.js";
import {
  dryRunRule,
  getRule,
  getRuleLibrary,
  getRunResults,
  saveRule,
  startRun,
  toRulePayload,
} from "./qualityRulesService.js";

const API_RULE = {
  ruleId: "R021",
  name: "amounts_in_range",
  description: "Amounts stay in range",
  template: "in_range",
  dimension: "validity",
  level: "row",
  params: { min: 0, max: 250000, boundsInclusive: true },
  appliesTo: null,
  nullPolicy: "ignore",
  rowFilter: null,
  threshold: { metric: "pass_rate", op: ">=", value: 0.995 },
  severity: "error",
  weight: 1,
  scope: {
    level: null,
    catalog: "main",
    schema: "sales*",
    table: "*",
    column: "*_amount",
    exclude: ["main.sales_tmp.*"],
    tableTypes: ["MANAGED", "VIEW"],
  },
  enabled: true,
  version: 3,
  lastRun: { runId: "run-1", at: "2026-09-26T06:10:00Z", counts: { FAIL: 1, PASS: 11, NO_DATA: 2, SKIPPED: 2 } },
};

function library(rules) {
  return {
    ok: true,
    data: {
      ok: true,
      data: { rules, totalRules: rules.length, failingRules: 1, lastRun: { runId: "run-1", completedAt: "2026-09-26T06:10:00Z" } },
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("rules", () => {
  it("groups the library by dimension in the design's order with status tones", async () => {
    api.listQualityRules.mockResolvedValue(
      library([
        { ...API_RULE, name: "orders_fresh", ruleId: "R003", template: "freshness_hours", dimension: "timeliness", lastRun: null },
        API_RULE,
        { ...API_RULE, name: "email_present", ruleId: "R005", dimension: "completeness", enabled: false },
      ]),
    );

    const { data } = await getRuleLibrary();

    expect(data.groups.map((g) => g.dimension)).toEqual(["Completeness", "Validity", "Timeliness"]);
    expect(data.groups[1].rules[0]).toEqual({
      ruleId: "R021",
      name: "amounts_in_range",
      template: "in_range",
      statusTone: "danger",
      disabled: false,
    });
    expect(data.groups[0].rules[0]).toMatchObject({ statusTone: "idle", disabled: true });
    expect(data.groups[2].rules[0].statusTone).toBe("idle");
    expect(data.lastRunLabel).toBe("06:10 UTC");
    expect(data.failingCount).toBe(1);
  });

  it("maps a rule into the editor's shape: percentages, toggles and an inferred scope level", async () => {
    api.listQualityRules.mockResolvedValue(library([API_RULE]));

    const { data } = await getRule("amounts_in_range");

    expect(data.threshold).toEqual({ metric: "pass_rate", op: ">=", value: 99.5, unit: "%" });
    expect(data.tableTypes).toEqual({ managed: true, external: false, view: true });
    expect(data.scope.level).toBe("schema");
    expect(data.lastRun).toMatchObject({ atLabel: "06:10 UTC", fail: 1, pass: 11, noData: 2, skipped: 2 });
    expect(await getRule("missing")).toEqual({ ok: false, error: "Rule not found" });
  });

  it("round-trips editor state back into the API payload", async () => {
    api.listQualityRules.mockResolvedValue(library([API_RULE]));
    const { data: draft } = await getRule("amounts_in_range");

    const payload = toRulePayload({ ...draft, weight: "2", threshold: { ...draft.threshold, value: "99.0" } });

    expect(payload.threshold).toEqual({ metric: "pass_rate", op: ">=", value: 0.99 });
    expect(payload.weight).toBe(2);
    expect(payload.scope).toEqual({
      level: "schema",
      catalog: "main",
      schema: "sales*",
      table: "*",
      column: "*_amount",
      exclude: ["main.sales_tmp.*"],
      tableTypes: ["MANAGED", "VIEW"],
    });
    expect(payload.rowFilter).toBeNull();
    expect(payload.version).toBe(3);
  });

  it("keeps value thresholds as-is and joins allowed values for the input", async () => {
    api.listQualityRules.mockResolvedValue(
      library([
        { ...API_RULE, name: "fresh", template: "freshness_hours", threshold: { metric: "value", op: "<=", value: 24 } },
        { ...API_RULE, name: "codes", template: "allowed_values", params: { values: ["USD", "EUR"], matchCase: true } },
      ]),
    );

    expect((await getRule("fresh")).data.threshold).toEqual({ metric: "value", op: "<=", value: 24, unit: "hours" });
    expect((await getRule("codes")).data.params.values).toBe("USD, EUR");
    expect(toRulePayload({ template: "freshness_hours", threshold: { metric: "value", op: "<=", value: "6" } }).threshold.value).toBe(6);
  });

  it("saves through PUT with the rule id and surfaces API errors", async () => {
    api.updateQualityRule.mockResolvedValue({ ok: true, data: { ok: true, data: { ...API_RULE, version: 4 } } });
    const saved = await saveRule({ ...API_RULE, ruleId: "R021", threshold: { metric: "pass_rate", op: ">=", value: 99 }, tableTypes: {} });

    expect(api.updateQualityRule.mock.calls[0][0]).toBe("R021");
    expect(saved.data.version).toBe(4);

    api.updateQualityRule.mockResolvedValue({ ok: false, error: "R021 was changed by someone else" });
    expect(await saveRule({ ...API_RULE, threshold: { metric: "pass_rate", value: 99 }, tableTypes: {} })).toEqual({
      ok: false,
      error: "R021 was changed by someone else",
    });
  });
});

describe("dry run", () => {
  it("maps the backend plan into the panel's rows", async () => {
    api.dryRunQualityRules.mockResolvedValue({
      ok: true,
      data: {
        ok: true,
        data: {
          tableCount: 8,
          bindingCount: 14,
          skippedCount: 7,
          excludedCount: 4,
          scanTableCount: 6,
          truncated: false,
          tables: [
            { fqn: "main.sales.orders", bindingCount: 4, columns: ["order_amount", "tax_amount"] },
            { fqn: "main.sales.summary", bindingCount: 1, columns: [] },
          ],
          skipped: [{ target: "main.sales.orders.raw_amount", rule: "r", reason: "type string not in [numeric, temporal]" }],
          errors: [{ target: "ops", message: "Couldn't list schemas: timeout" }],
          bindingErrors: [],
          scan: { target: "main.sales.orders", sql: "SELECT count(1) AS __rows", passCount: 1 },
        },
      },
    });

    const { data } = await dryRunRule({ template: "in_range", threshold: { metric: "pass_rate", value: 99 }, tableTypes: {} });

    expect(data).toMatchObject({
      tables: "8",
      bindings: "14",
      skipped: "7",
      excluded: "4",
      moreTables: "+ 6 more tables",
      moreSkips: "+ 6 more columns",
      sql: "SELECT count(1) AS __rows",
      scanOf: "Scan 1 of 6",
      runLabel: "Run on 8 tables",
      problems: ["ops: Couldn't list schemas: timeout"],
    });
    expect(data.rows[1].columns).toBe("table-level");
    expect(data.skips[0]).toEqual({ column: "main.sales.orders.raw_amount", reason: "type string not in [numeric, temporal]" });
  });
});

describe("runs", () => {
  it("only sends the options that were filled in", async () => {
    api.startQualityRun.mockResolvedValue({ ok: true, data: { ok: true, data: { runId: "x" } } });

    await startRun({ ruleIds: ["R021"], where: "  ", sampleFraction: null, maxParallelTables: "4" });

    expect(api.startQualityRun).toHaveBeenCalledWith({ ruleIds: ["R021"], maxParallelTables: 4 });
  });

  it("builds tiles, tree and rows for the latest run", async () => {
    api.fetchQualityRun.mockResolvedValue({
      ok: true,
      data: {
        ok: true,
        data: {
          run: {
            runId: "run-2", status: "done", completedAt: "2026-09-26T06:10:00Z", durationMs: 252000,
            ruleCount: 14, tableCount: 58, resultCount: 4, where: null, sampleFraction: null, ruleIds: null,
          },
          kpis: { rowWeighted: 0.9964, tableAverage: 0.9921, thresholdsMet: 2, thresholdsEvaluated: 3, resultCount: 4 },
          previous: { runId: "run-1", kpis: { rowWeighted: 0.9972, tableAverage: 0.99, thresholdsMet: 3 } },
          worstSeverity: { severity: "error", bindings: 1, rules: 1, errors: 0 },
          statusCounts: { FAIL: 1, ERROR: 0, WARN: 0, NO_DATA: 0, PASS: 2, SKIPPED: 1, attention: 1, ALL: 4 },
          dimensions: [{ dimension: "timeliness", met: 1, total: 2 }],
          tree: [
            {
              name: "main", kind: "catalog", rowWeighted: 0.9964, simpleAverage: 0.9921, bindings: 3, notPassing: 1, worstStatus: "FAIL",
              children: [
                {
                  name: "sales", kind: "schema", rowWeighted: 0.9964, simpleAverage: 0.9921, bindings: 3, notPassing: 1, worstStatus: "FAIL",
                  children: [{ name: "refunds", kind: "table", rowWeighted: null, simpleAverage: null, bindings: 1, notPassing: 1, worstStatus: "NO_DATA" }],
                },
              ],
            },
          ],
        },
      },
    });
    api.fetchQualityRunResults.mockResolvedValue({
      ok: true,
      data: {
        ok: true,
        data: {
          items: [
            {
              status: "FAIL", ruleName: "orders_fresh", template: "freshness_hours", target: "main.sales.orders.updated_at",
              totalCount: 18406221, failCount: null, metricValue: 31.24, level: "aggregate",
              threshold: { metric: "value", op: "<=", value: 24 }, message: null,
            },
            {
              status: "PASS", ruleName: "customer_id_not_null", template: "not_null", target: "main.sales.customers.customer_id",
              totalCount: 2418904, failCount: 0, metricValue: 1, level: "row",
              threshold: { metric: "pass_rate", op: ">=", value: 0.995 }, message: null,
            },
            {
              status: "PASS", ruleName: "orders_rows", template: "row_count", target: "main.sales.orders",
              totalCount: 18406221, failCount: null, metricValue: 18406221, level: "table",
              threshold: { metric: "value", op: ">=", value: 1 }, message: null,
            },
          ],
        },
      },
    });

    const { data } = await getRunResults();

    expect(api.fetchQualityRun).toHaveBeenCalledWith("latest");
    expect(data.summary).toMatchObject({ atLabel: "2026-09-26 06:10 UTC", durationLabel: "4m 12s", scanLabel: "full scan · not sampled", failing: 1 });
    expect(data.kpiTiles.map((t) => [t.value, t.deltaLabel])).toEqual([["99.64", "0.08"], ["99.21", ""], ["2", "1"]]);
    expect(data.kpiTiles[2].unit).toBe(" / 3");
    expect(data.worstSeverity.bindingsLabel).toBe("1 binding · 1 rule");
    expect(data.rollupTree[0]).toMatchObject({ name: "main", kind: "catalog", statusTone: "danger", depth: 0, expanded: true });
    expect(data.rollupTree[0].rowWeighted).toBeCloseTo(99.64);
    expect(data.rollupTree[0].children[0].children[0]).toEqual({
      name: "refunds", kind: "no data", statusTone: "idle", rowWeighted: null, simpleAvg: null, bindings: 1, notPassing: 1, depth: 2,
    });
    expect(data.dimensionThresholds).toEqual([{ dimension: "Timeliness", met: 1, total: 2, tone: "danger" }]);
    expect(data.statusBreakdown.find((b) => b.status === "PASS")).toMatchObject({ count: 2, pct: 50 });
    expect(data.resultRows[0]).toMatchObject({ metric: "31.2 h", threshold: "≤ 24 h", failing: "—", total: "18,406,221", message: "—" });
    expect(data.resultRows[1]).toMatchObject({ metric: "100.00%", threshold: "≥ 99.5%" });
    expect(data.resultRows[2]).toMatchObject({ metric: "18.4M", threshold: "≥ 1", message: "Table-level" });
    expect(data.resultTotals.attention).toBe(1);
  });

  it("reports a missing run as an error", async () => {
    api.fetchQualityRun.mockResolvedValue({ ok: false, error: "Run not found" });
    api.fetchQualityRunResults.mockResolvedValue({ ok: false, error: "Run not found" });

    expect(await getRunResults()).toEqual({ ok: false, error: "Run not found" });
  });
});
