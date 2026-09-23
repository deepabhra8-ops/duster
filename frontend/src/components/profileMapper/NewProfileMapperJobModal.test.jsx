import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock("../../api/api.js", () => ({
  createDraftJob: vi.fn(),
  listConnectionSchemas: vi.fn(),
  updateJobTables: vi.fn(),
  uploadFile: vi.fn(),
  listConnections: vi.fn(),
}));

vi.mock("../../hooks/useToast.js", () => ({
  useToast: () => ({ showToast }),
}));

import * as api from "../../api/api.js";
import NewProfileMapperJobModal from "./NewProfileMapperJobModal.jsx";

const csv = (name) => new File(["id,name\n1,a\n"], name, { type: "text/csv" });

function setup() {
  const onCreated = vi.fn();
  render(<NewProfileMapperJobModal open onClose={vi.fn()} onCreated={onCreated} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Sales profile" } });
  return { onCreated };
}

const pick = (...files) =>
  fireEvent.change(screen.getByLabelText("Data Files"), { target: { files } });

const create = () => fireEvent.click(screen.getByRole("button", { name: "Create" }));

beforeEach(() => {
  vi.clearAllMocks();
  api.listConnections.mockResolvedValue({ ok: true, data: { data: [] } });
  api.createDraftJob.mockResolvedValue({ ok: true, data: { job_id: "job-1" } });
  api.updateJobTables.mockResolvedValue({ ok: true });
  api.uploadFile.mockImplementation(async (file) => ({
    ok: true,
    data: { filename: `uuid_${file.name}` },
  }));
});

describe("picking files", () => {
  it("lists every picked file, across several picks", () => {
    setup();

    pick(csv("customers.csv"), csv("orders.csv"));
    pick(csv("products.csv"));

    expect(screen.getByText("customers.csv")).toBeInTheDocument();
    expect(screen.getByText("orders.csv")).toBeInTheDocument();
    expect(screen.getByText("products.csv")).toBeInTheDocument();
  });

  it("refuses a second file with the same name, ignoring case", () => {
    setup();

    pick(csv("customers.csv"));
    pick(csv("Customers.CSV"));

    expect(screen.getByText(/"Customers.CSV" is already added/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Remove / })).toHaveLength(1);
  });

  it("keeps the valid files when the same selection also has a bad one", () => {
    setup();

    pick(csv("notes.txt"), csv("orders.csv"));

    expect(screen.getByText(/"notes.txt" is not a .csv file/)).toBeInTheDocument();
    expect(screen.getByText("orders.csv")).toBeInTheDocument();
  });

  it("removes only the file whose ✕ was clicked", () => {
    setup();
    pick(csv("customers.csv"), csv("orders.csv"));

    fireEvent.click(screen.getByRole("button", { name: "Remove customers.csv" }));

    expect(screen.queryByText("customers.csv")).not.toBeInTheDocument();
    expect(screen.getByText("orders.csv")).toBeInTheDocument();
  });

  it("requires at least one file", async () => {
    setup();

    create();

    expect(await screen.findByText(/Choose at least one CSV file/)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });
});

describe("creating the job", () => {
  it("uploads every file and attaches each as its own table in one call", async () => {
    const { onCreated } = setup();
    pick(csv("customers.csv"), csv("orders.csv"));

    create();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.uploadFile).toHaveBeenCalledTimes(2);
    expect(api.updateJobTables).toHaveBeenCalledTimes(1);
    expect(api.updateJobTables).toHaveBeenCalledWith("job-1", [
      { name: "customers", file: "uuid_customers.csv", primary_key: "" },
      { name: "orders", file: "uuid_orders.csv", primary_key: "" },
    ]);
    expect(showToast).not.toHaveBeenCalled();
  });

  it("names the file that failed to upload and keeps the others", async () => {
    api.uploadFile.mockImplementation(async (file) =>
      file.name === "orders.csv"
        ? { ok: false, error: "File exceeds the 200 MB limit" }
        : { ok: true, data: { filename: `uuid_${file.name}` } }
    );
    const { onCreated } = setup();
    pick(csv("customers.csv"), csv("orders.csv"), csv("products.csv"));

    create();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.updateJobTables).toHaveBeenCalledWith("job-1", [
      { name: "customers", file: "uuid_customers.csv", primary_key: "" },
      { name: "products", file: "uuid_products.csv", primary_key: "" },
    ]);
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "warn",
        title: "1 of 3 files weren't uploaded",
        message: expect.stringContaining('"orders.csv"'),
      })
    );
  });

  it("warns when the backend refuses the tables", async () => {
    api.updateJobTables.mockResolvedValue({ ok: false, error: "More than one source table is named 'x'" });
    const { onCreated } = setup();
    pick(csv("customers.csv"));

    create();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Job created, but files weren't attached",
        message: expect.stringContaining("More than one source table"),
      })
    );
  });
});
