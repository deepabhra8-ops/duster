import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../hooks/useHealthCheck.js", () => ({
  useHealthCheck: () => true,
}));

vi.mock("../../hooks/useDashboardSummary.js", () => ({
  useDashboardSummary: () => ({
    data: {
      jobsTotal: 12,
      jobsActive: 2,
      connectionsCount: 3,
      latestScore: 92,
      scoreTrend: [{ score: 88 }, { score: 92 }],
      recentJobs: [
        { job_id: "j1", name: "orders-scan", step: "3", status: "done", started: "2026-09-23T00:00:00Z" },
      ],
    },
    loading: false,
  }),
}));

vi.mock("../../hooks/useConnectionsList.js", () => ({
  useConnectionsList: () => ({
    data: [{ id: "c1", name: "prod-postgres", dbType: "postgres" }],
    loading: false,
  }),
}));

vi.mock("../../hooks/useDimensionsSummary.js", () => ({
  useDimensionsSummary: () => ({
    data: {
      scoringCadenceLabel: "Scored nightly · last run 6h ago",
      dimensions: [
        { id: "completeness", label: "Completeness", score: 97, deltaLabel: "1.2", deltaDirection: "up", trend: [90, 92, 94, 96, 97] },
        { id: "timeliness", label: "Timeliness", score: 84, deltaLabel: "6.4", deltaDirection: "down", trend: [96, 92, 88, 86, 84] },
      ],
      lowestScoringSources: [{ id: "billing-mysql", name: "billing-mysql", score: 61, deltaLabel: "9", deltaDirection: "down" }],
      criticalElements: [
        {
          id: "customers-ssn",
          name: "customers.ssn",
          source: "prod-postgres",
          dimension: "Completeness",
          score: 71,
          severity: "High",
          impacts: [{ name: "KYC Compliance", kind: "report" }],
        },
      ],
      compositeTrend: { points: [90, 88, 86, 88, 90], target: 90, anomalyIndex: 2, anomalyLabel: "Incident", startLabel: "Wk 1", endLabel: "Wk 5" },
      businessImpact: {
        totalAtRisk: "$142K",
        caption: "estimated exposure this quarter",
        goals: [{ id: "goal-1", name: "Revenue reporting accuracy", sub: "Blocked by Accuracy", value: "$96K" }],
      },
    },
    loading: false,
  }),
}));

import DashboardPage from "./DashboardPage.jsx";

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>
  );
}

describe("DashboardPage", () => {
  it("renders the dimension tiles, a ranking row, a critical element, and a recent job", () => {
    renderPage();

    expect(screen.getByText("Completeness")).toBeInTheDocument();
    expect(screen.getByText("Timeliness")).toBeInTheDocument();
    expect(screen.getByText("billing-mysql")).toBeInTheDocument();
    expect(screen.getByText("customers.ssn")).toBeInTheDocument();
    expect(screen.getByText("orders-scan")).toBeInTheDocument();
  });

  it("shows the real connection count in the subtitle, not a fabricated one", () => {
    renderPage();

    expect(screen.getByText(/across all 1 connection/)).toBeInTheDocument();
  });
});
