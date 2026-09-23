import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/api.js", () => ({
  inspectProfileMapWorkbook: vi.fn(),
  createDraftJob: vi.fn(),
  updateJobTables: vi.fn(),
  listConnectionSchemas: vi.fn(),
  createValidatorJobFromProfileMap: vi.fn(),
  listConnections: vi.fn(),
  listConnectionTables: vi.fn(),
  listConnectionColumns: vi.fn(),
  listJobs: vi.fn(),
  sampleLovUrl: vi.fn(() => "/api/sample-lov"),
  getLov: vi.fn(),
  uploadFile: vi.fn(),
}));

import * as api from "../../api/api.js";
import { ToastProvider } from "../../contexts/ToastContext.jsx";
import NewValidatorJobModal from "./NewValidatorJobModal.jsx";
import { ToastProvider } from "../../contexts/ToastContext.jsx";

const WORKBOOK = new File(["x"], "map.xlsx", {
  type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
});

function renderModal(props = {}) {
  return render(
    <ToastProvider>
      <NewValidatorJobModal open onClose={vi.fn()} onCreated={vi.fn()} {...props} />
    </ToastProvider>
  );
}

function setup() {
  const onCreated = vi.fn();
  renderModal({ onCreated });
  return { onCreated };
}

const create = () => {
  const next = screen.queryByRole("button", { name: /Next/ });
  fireEvent.click(next || screen.getByRole("button", { name: "Create" }));
};

const goToTableStep = () => fireEvent.click(screen.getByRole("button", { name: /Next/ }));

const pickDataSource = () => fireEvent.click(screen.getByRole("radio", { name: "Data Source" }));

async function uploadWorkbook(tables = ["claim"]) {
  api.inspectProfileMapWorkbook.mockResolvedValue({
    ok: true,
    data: {
      filename: "abc123_map.xlsx",
      tables: tables.map((t) => ({ table_name: t, columns: [] })),
    },
  });

  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
  pickDataSource();
  fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));
  fireEvent.change(screen.getByLabelText("Mapping Workbook"), {
    target: { files: [WORKBOOK] },
  });

  await screen.findByText(new RegExp(`Found ${tables.length} table`, "i"));
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listConnections.mockResolvedValue({
    ok: true,
    data: { data: [{ id: "c1", name: "Warehouse", db_type: "postgresql" }] },
  });
  api.listJobs.mockResolvedValue({ ok: true, data: { jobs: [] } });
  api.listConnectionSchemas.mockResolvedValue({ ok: true, data: { schemas: ["public"] } });
  api.listConnectionTables.mockResolvedValue({ ok: true, data: { tables: ["claim"] } });
  api.listConnectionColumns.mockResolvedValue({ ok: true, data: { columns: ["claim_id"] } });
  api.createDraftJob.mockResolvedValue({ ok: true, data: { job_id: "job-1" } });
  api.updateJobTables.mockResolvedValue({ ok: true });
});

describe("guards before anything is created", () => {
  it("requires a name", async () => {
    setup();

    create();

    expect(await screen.findByText(/Name is required/)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });

  it("requires a workbook in upload mode", async () => {
    setup();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    pickDataSource();
    fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));
    create();

    expect(await screen.findByText(/Choose a mapping workbook first/i)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });

  it("requires a connection once a workbook is uploaded", async () => {
    setup();
    await uploadWorkbook();
    goToTableStep();

    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText(/Select the saved connection/i)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });
});

describe("the uploaded workbook", () => {
  it("shows which tables it contains, so the user knows what to pick", async () => {
    setup();
    await uploadWorkbook(["claim", "member"]);

    expect(screen.getByText("claim")).toBeInTheDocument();
    expect(screen.getByText("member")).toBeInTheDocument();
  });

  it("offers a connection picker only in upload mode", async () => {
    setup();

    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();

    await uploadWorkbook();

    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();
    goToTableStep();
    expect(screen.getByText("Source Connection")).toBeInTheDocument();
  });

  it("loads the schemas of a picked connection", async () => {
    setup();
    await uploadWorkbook();
    goToTableStep();

    fireEvent.focus(screen.getByPlaceholderText(/Search saved connections/i));
    fireEvent.click(await screen.findByText("Warehouse (postgresql)"));

    await waitFor(() => expect(api.listConnectionSchemas).toHaveBeenCalledWith("c1"));
  });
});

describe("the profile-mapper-job path still works", () => {
  it("requires a picked profile map", async () => {
    setup();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    create();

    expect(await screen.findByText(/Select a completed profile map/)).toBeInTheDocument();
    expect(api.createValidatorJobFromProfileMap).not.toHaveBeenCalled();
  });
});

describe("a rejected workbook keeps its reason on screen", () => {
  async function uploadAndFail(reason) {
    api.inspectProfileMapWorkbook.mockResolvedValue({ ok: false, error: reason });

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    pickDataSource();
    fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));
    fireEvent.change(screen.getByLabelText("Mapping Workbook"), {
      target: { files: [WORKBOOK] },
    });

    await screen.findByText(new RegExp(reason));
  }

  it("survives toggling the source mode", async () => {
    setup();
    await uploadAndFail("File content is not a valid .xlsx");

    fireEvent.click(screen.getByLabelText("From a Profile Mapper job"));
    fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));

    expect(screen.getByText(/not a valid .xlsx/)).toBeInTheDocument();
  });

  it("tells the user the file was rejected rather than missing", async () => {
    setup();
    await uploadAndFail("No tables found in this workbook");

    create();

    expect(await screen.findByText(/was not accepted/)).toBeInTheDocument();
  });

  it("clears once a different file is accepted", async () => {
    setup();
    await uploadAndFail("No tables found in this workbook");

    api.inspectProfileMapWorkbook.mockResolvedValue({
      ok: true,
      data: { filename: "ok_map.xlsx", tables: [{ table_name: "claim", columns: [] }] },
    });
    fireEvent.change(screen.getByLabelText("Mapping Workbook"), {
      target: { files: [WORKBOOK] },
    });

    await screen.findByText(/Found 1 table/i);
    expect(screen.queryByText(/No tables found/)).not.toBeInTheDocument();
  });
});

describe("the two-step wizard", () => {
  it("offers Create, not Next, when the source is a completed run", () => {
    setup();

    expect(screen.queryByRole("button", { name: /Next/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
  });

  it("offers Next, not Create, on the upload path", () => {
    setup();
    pickDataSource();
    fireEvent.click(screen.getByLabelText(/upload a mapping workbook/i));

    expect(screen.getByRole("button", { name: /Next/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
  });

  it("keeps a step-1 problem on step 1 rather than advancing", async () => {
    setup();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    pickDataSource();
    fireEvent.click(screen.getByLabelText(/upload a mapping workbook/i));

    create();

    expect(await screen.findByText(/Choose a mapping workbook first/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeVisible();
    expect(screen.getByRole("button", { name: /Next/ })).toBeInTheDocument();
  });
});

describe("stepping back and forward again", () => {
  async function pickTableAndKey() {
    await uploadWorkbook();
    goToTableStep();

    fireEvent.focus(screen.getByPlaceholderText(/Search saved connections/i));
    fireEvent.click(await screen.findByText("Warehouse (postgresql)"));

    fireEvent.click(await screen.findByRole("button", { name: /public/ }));
    fireEvent.click(await screen.findByRole("checkbox"));

    const key = await screen.findByPlaceholderText(/Search primary key/i);
    fireEvent.focus(key);
    fireEvent.click(await screen.findByText("claim_id"));

    await waitFor(() => expect(screen.getByDisplayValue("claim_id")).toBeInTheDocument());
  }

  it("brings the chosen primary key back instead of loading forever", async () => {
    setup();
    await pickTableAndKey();

    fireEvent.click(screen.getByRole("button", { name: /Back/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    await waitFor(() => expect(screen.getByDisplayValue("claim_id")).toBeInTheDocument());
    expect(screen.queryByPlaceholderText("Loading…")).not.toBeInTheDocument();
  });
});

describe("arriving from a profile map's results page", () => {
  it("pre-selects the source job and stays on the job mode", async () => {
    api.listJobs.mockResolvedValue({
      ok: true,
      data: { jobs: [{ job_id: "pm-7", name: "Claims Profile", status: "done" }] },
    });

    renderModal({ initialSourceJobId: "pm-7" });

    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    create();

    await waitFor(() =>
      expect(screen.queryByText(/Select a completed profile map/)).not.toBeInTheDocument()
    );
    await waitFor(() =>
      expect(api.createValidatorJobFromProfileMap).toHaveBeenCalledWith(
        "Claims DQ",
        "",
        "pm-7",
        null
      )
    );
  });

  it("does not pre-select anything when opened normally", async () => {
    setup();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    create();

    expect(await screen.findByText(/Select a completed profile map/)).toBeInTheDocument();
  });
});

describe("the source type radio", () => {
  const typeGroup = () => screen.getByRole("radiogroup", { name: "Source type" });
  const flatFile = () => screen.getByRole("radio", { name: "Flat File" });
  const dataSource = () => screen.getByRole("radio", { name: "Data Source" });

  it("offers Flat File and Data Source, with Flat File picked", () => {
    setup();

    expect(typeGroup()).toContainElement(flatFile());
    expect(typeGroup()).toContainElement(dataSource());
    expect(flatFile()).toBeChecked();
    expect(dataSource()).not.toBeChecked();
  });

  it("sits before the source cards", () => {
    setup();

    const cards = screen.getByRole("radiogroup", { name: "Choose a source" });

    expect(
      typeGroup().compareDocumentPosition(cards) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("switches between the two options, one at a time", () => {
    setup();

    fireEvent.click(dataSource());
    expect(dataSource()).toBeChecked();
    expect(flatFile()).not.toBeChecked();

    fireEvent.click(flatFile());
    expect(flatFile()).toBeChecked();
    expect(dataSource()).not.toBeChecked();
  });

  it("offers only the Profile Mapper Job card for Flat File", () => {
    setup();

    expect(screen.getByLabelText("From a Profile Mapper job")).toBeChecked();
    expect(screen.queryByLabelText("Upload a mapping workbook")).not.toBeInTheDocument();
    expect(screen.queryByText("Mapping Workbook")).not.toBeInTheDocument();
    expect(screen.getByText("Select profile map")).toBeInTheDocument();
  });

  it("offers both cards for Data Source", () => {
    setup();
    pickDataSource();

    expect(screen.getByLabelText("From a Profile Mapper job")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload a mapping workbook")).toBeInTheDocument();
  });

  it("drops the workbook path when Flat File is picked, and restores it on the way back", () => {
    setup();
    pickDataSource();
    fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));
    expect(screen.getByText("Upload mapping workbook")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Next/ })).toBeInTheDocument();

    fireEvent.click(flatFile());

    expect(screen.queryByLabelText("Upload a mapping workbook")).not.toBeInTheDocument();
    expect(screen.queryByText("Upload mapping workbook")).not.toBeInTheDocument();
    expect(screen.getByLabelText("From a Profile Mapper job")).toBeChecked();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();

    pickDataSource();

    expect(screen.getByLabelText("Upload a mapping workbook")).toBeChecked();
  });

  it("validates as a profile-map run once Flat File is picked", async () => {
    setup();
    pickDataSource();
    fireEvent.click(screen.getByLabelText("Upload a mapping workbook"));
    fireEvent.click(flatFile());
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });

    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText(/Select a completed profile map/)).toBeInTheDocument();
    expect(screen.queryByText(/Choose a mapping workbook first/)).not.toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });
});
