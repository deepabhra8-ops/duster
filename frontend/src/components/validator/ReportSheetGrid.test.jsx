/**
 * ReportSheetGrid - how a check that could not run is presented.
 *
 * The regression: a rule that cannot execute (no reference list, no configured
 * columns, a crash) reports an all-pass mask, whose score is 1.0. The grid used
 * to render that as "100.0%", telling the customer a check had passed when it
 * had never run. It must read NOT RUN instead, and must keep showing a real
 * percentage for checks that did run.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ReportSheetGrid from "./ReportSheetGrid.jsx";

const okRow = {
  table: "claim",
  column: "claim_id",
  cde: true,
  ruleId: "DQ1",
  ruleNotes: "Value must not be null",
  invalidCount: 0,
  totalCount: 100,
  score: 1,
  status: "ok",
};

const notRunRow = {
  table: "claim",
  column: "status",
  cde: false,
  ruleId: "DQ8",
  ruleNotes: "Reference list 'statuses' was not found - check not run",
  invalidCount: 0,
  totalCount: 100,
  score: null,
  status: "not_run",
};

function rowFor(ruleId) {
  return screen.getByText(ruleId).closest("tr");
}

describe("a check that could not run", () => {
  it("shows NOT RUN instead of a score", () => {
    render(<ReportSheetGrid rows={[notRunRow]} />);

    expect(within(rowFor("DQ8")).getByText("NOT RUN")).toBeInTheDocument();
  });

  it("never renders it as a perfect score", () => {
    render(<ReportSheetGrid rows={[notRunRow]} />);

    expect(screen.queryByText("100.0%")).not.toBeInTheDocument();
  });

  it("keeps the reason available", () => {
    render(<ReportSheetGrid rows={[notRunRow]} />);

    expect(screen.getByText(/check not run/)).toBeInTheDocument();
  });

  it("draws no score bar, because there is no measurement", () => {
    const { container } = render(<ReportSheetGrid rows={[notRunRow]} />);

    expect(container.querySelectorAll(".bar")).toHaveLength(0);
  });
});

describe("a check that ran", () => {
  it("shows its percentage", () => {
    render(<ReportSheetGrid rows={[okRow]} />);

    expect(within(rowFor("DQ1")).getByText("100.0%")).toBeInTheDocument();
  });

  it("is unaffected by a not-run row beside it", () => {
    render(<ReportSheetGrid rows={[okRow, notRunRow]} />);

    expect(within(rowFor("DQ1")).getByText("100.0%")).toBeInTheDocument();
    expect(within(rowFor("DQ8")).getByText("NOT RUN")).toBeInTheDocument();
  });
});

describe("backward compatibility", () => {
  it("treats a row with no status key as a real result", () => {
    // Summaries stored by an engine build that predates the status field must
    // keep rendering their scores rather than all turning into NOT RUN.
    const legacy = { ...okRow, score: 0.97 };
    delete legacy.status;

    render(<ReportSheetGrid rows={[legacy]} />);

    expect(screen.getByText("97.0%")).toBeInTheDocument();
    expect(screen.queryByText("NOT RUN")).not.toBeInTheDocument();
  });

  it("treats a null score with no status as not run", () => {
    const legacy = { ...okRow, score: null };
    delete legacy.status;

    render(<ReportSheetGrid rows={[legacy]} />);

    expect(screen.getByText("NOT RUN")).toBeInTheDocument();
  });
});

describe("other states", () => {
  it("shows an empty state when there are no rows", () => {
    render(<ReportSheetGrid rows={[]} />);

    expect(screen.getByText(/No rows for this sheet/)).toBeInTheDocument();
  });

  it("renders skeleton rows while loading, under the real headers", () => {
    const { container } = render(<ReportSheetGrid rows={[]} loading />);

    expect(screen.getByText("Rule Notes")).toBeInTheDocument();
    expect(container.querySelectorAll(".skeleton-cell").length).toBeGreaterThan(0);
  });
});
