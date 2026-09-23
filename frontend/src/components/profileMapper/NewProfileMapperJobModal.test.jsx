import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));

vi.mock("../../api/api.js", () => ({
  createDraftJob: vi.fn(),
  listConnectionSchemas: vi.fn(),
  listConnectionTables: vi.fn(),
  listConnectionColumns: vi.fn(),
  updateJobTables: vi.fn(),
  listConnections: vi.fn(),
}));

vi.mock("../../hooks/useToast.js", () => ({
  useToast: () => ({ showToast }),
}));

import * as api from "../../api/api.js";
import NewProfileMapperJobModal from "./NewProfileMapperJobModal.jsx";

function setup() {
  const onCreated = vi.fn();
  render(<NewProfileMapperJobModal open onClose={vi.fn()} onCreated={onCreated} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Sales profile" } });
  return { onCreated };
}

const goNext = () => fireEvent.click(screen.getByRole("button", { name: /Next/ }));
const create = () => fireEvent.click(screen.getByRole("button", { name: "Create" }));

async function pickConnection() {
  fireEvent.focus(await screen.findByPlaceholderText(/Search saved connections/i));
  fireEvent.click(await screen.findByText("Warehouse (postgresql)"));
}

async function pickTableAndColumn() {
  await pickConnection();
  fireEvent.click(await screen.findByRole("button", { name: /public/ }));
  fireEvent.click(await screen.findByRole("checkbox"));

  const column = await screen.findByPlaceholderText(/Search cde/i);
  fireEvent.focus(column);
  fireEvent.click(await screen.findByText("claim_id"));

  await waitFor(() => expect(screen.getByDisplayValue("claim_id")).toBeInTheDocument());
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listConnections.mockResolvedValue({
    ok: true,
    data: { data: [{ id: "c1", name: "Warehouse", db_type: "postgresql" }] },
  });
  api.listConnectionSchemas.mockResolvedValue({ ok: true, data: { schemas: ["public"] } });
  api.listConnectionTables.mockResolvedValue({ ok: true, data: { tables: ["claim"] } });
  api.listConnectionColumns.mockResolvedValue({ ok: true, data: { columns: ["claim_id"] } });
  api.createDraftJob.mockResolvedValue({ ok: true, data: { job_id: "job-1" } });
  api.updateJobTables.mockResolvedValue({ ok: true });
});

describe("step 1 - details", () => {
  it("requires a name before moving on", () => {
    render(<NewProfileMapperJobModal open onClose={vi.fn()} onCreated={vi.fn()} />);

    goNext();

    expect(screen.getByText(/Name is required/)).toBeInTheDocument();
  });

  it("moves to table selection once named", () => {
    setup();

    goNext();

    expect(screen.getByText(/Select Tables/)).toBeInTheDocument();
    expect(screen.getByText("Select Saved Connection")).toBeInTheDocument();
  });
});

describe("step 2 - connection and tables", () => {
  it("requires a saved connection before creating", async () => {
    setup();
    goNext();

    create();

    expect(await screen.findByText(/Select a saved connection/)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });

  it("requires at least one locked table with a CDE column", async () => {
    setup();
    goNext();
    await pickConnection();

    create();

    await waitFor(() =>
      expect(showToast).toHaveBeenCalledWith(
        expect.objectContaining({ type: "error", title: "No table selected" })
      )
    );
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });

  it("creates the job and attaches the selected table", async () => {
    const { onCreated } = setup();
    goNext();
    await pickTableAndColumn();

    create();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(api.createDraftJob).toHaveBeenCalledWith("Sales profile", "", "c1", "1");
    expect(api.updateJobTables).toHaveBeenCalledWith("job-1", [
      { schema: "public", name: "claim", primary_key: "claim_id" },
    ]);
    expect(showToast).not.toHaveBeenCalled();
  });

  it("loads the schemas of a picked connection", async () => {
    setup();
    goNext();

    await pickConnection();

    await waitFor(() => expect(api.listConnectionSchemas).toHaveBeenCalledWith("c1"));
  });
});

describe("stepping back and forward again", () => {
  it("brings the chosen column back instead of loading forever", async () => {
    setup();
    goNext();
    await pickTableAndColumn();

    fireEvent.click(screen.getByRole("button", { name: /Back/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    await waitFor(() => expect(screen.getByDisplayValue("claim_id")).toBeInTheDocument());
  });
});
