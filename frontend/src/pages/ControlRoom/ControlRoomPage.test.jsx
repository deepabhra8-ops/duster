import { render, screen } from "@testing-library/react";
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

import ControlRoomPage from "./ControlRoomPage.jsx";

describe("ControlRoomPage", () => {
  it("renders the KPI row, a connection, and a recent job", () => {
    render(<ControlRoomPage />);

    expect(screen.getByText("Total jobs")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("prod-postgres")).toBeInTheDocument();
    expect(screen.getByText("orders-scan")).toBeInTheDocument();
  });
});
