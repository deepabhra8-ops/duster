import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock("../api/api.js", () => ({
  fetchJob: vi.fn(),
  fetchProfileMap: vi.fn(),
  updateProfileMapCells: vi.fn(),
  http: vi.fn(),
  TRANSFER_TIMEOUT: 30000,
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ jobId: "job-1" }),
  useNavigate: () => vi.fn(),
}));

vi.mock("../hooks/useToast.js", () => ({
  useToast: () => ({ showToast }),
}));

vi.mock("../components/profileMapper/ExpandableColumnRow.jsx", () => ({
  default: () => <tr><td>row</td></tr>,
}));

import { fetchJob, fetchProfileMap } from "../api/api.js";
import ProfileMapperJob from "./ProfileMapperJob.jsx";

function makeRow(table, totalCount, column) {
  return {
    Table: table,
    Column: column,
    "Data Type": "int",
    "Total Count": totalCount,
    "Null Count": 0,
    "Null %": "0.00%",
    "Distinct Count": totalCount,
    "Unique %": "100.00%",
    "Min Value": 1,
    "Max Value": totalCount,
    "Applicable Rules": "not_null",
  };
}

describe("ProfileMapperJob - Rows Analyzed card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchJob.mockResolvedValue({
      ok: true,
      data: { job_id: "job-1", name: "Test job", status: "done", has_profile: true },
    });
  });

  it("sums each distinct table's row count instead of using the first row's", async () => {
    fetchProfileMap.mockResolvedValue({
      ok: true,
      data: {
        version: 1,
        rows: [
          makeRow("Customer", 30, "CustomerID"),
          makeRow("OrderInfo", 2291, "OrderID"),
          makeRow("OrderInfo", 2291, "CustomerID"),
        ],
      },
    });

    render(<ProfileMapperJob />);

    await waitFor(() => {
      const card = screen.getByText("Rows Analyzed").closest(".summary-card");
      expect(card).toHaveTextContent("2,321");
    });
  });
});

describe("ProfileMapperJob - one tab per table", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchJob.mockResolvedValue({
      ok: true,
      data: {
        job_id: "job-1",
        name: "Sales tables",
        status: "done",
        has_profile: true,
      },
    });
  });

  it("labels each tab with its table's column count", async () => {
    fetchProfileMap.mockResolvedValue({
      ok: true,
      data: {
        version: 1,
        rows: [
          makeRow("customers", 10, "id"),
          makeRow("customers", 10, "name"),
          makeRow("orders", 5, "id"),
        ],
      },
    });

    render(<ProfileMapperJob />);

    expect(await screen.findByRole("tab", { name: "customers (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "orders (1)" })).toBeInTheDocument();
  });

  it("names the table the run had to skip in a toast", async () => {
    fetchProfileMap.mockResolvedValue({
      ok: true,
      data: {
        version: 1,
        rows: [makeRow("customers", 10, "id")],
        failed_tables: [{ table: "orders", error: "Path does not exist" }],
      },
    });

    render(<ProfileMapperJob />);

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "warn",
          title: "1 table couldn't be profiled",
          message: expect.stringContaining('"orders"'),
        })
      )
    );
    expect(screen.queryByRole("tab", { name: /orders/ })).not.toBeInTheDocument();
  });

  it("stays quiet when every table profiled", async () => {
    fetchProfileMap.mockResolvedValue({
      ok: true,
      data: { version: 1, rows: [makeRow("customers", 10, "id")], failed_tables: [] },
    });

    render(<ProfileMapperJob />);

    await screen.findByRole("tab", { name: "customers (1)" });
    expect(showToast).not.toHaveBeenCalled();
  });
});
