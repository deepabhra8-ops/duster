/**
 * NewValidatorJobModal - the "Upload a mapping workbook" path.
 *
 * The regression: a validation run needs a profile map AND a source connection,
 * but this mode only ever collected the map. It posted connection_id: null and
 * `tables` as a list of bare table-name STRINGS, so the draft it created could
 * never run - config_builder._build_tables calls table.get("name") on each entry
 * and raised "'str' object has no attribute 'get'", and with no connection the
 * generated config carried no source.db or connection_string either. The user saw
 * a job that failed inside Glue, with no indication the form had been incomplete.
 *
 * These tests pin the guards that stop an incomplete job being created at all.
 * fireEvent rather than user-event: this repo does not depend on the latter, and
 * adding a devDependency to test a modal is not worth it.
 */
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
  // LovUploadPanel's imports. sampleLovUrl runs during render, so it has to
  // return something; getLov only runs once a LOV is chosen, uploadFile on upload.
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

/* The modal embeds LovUploadPanel, which calls useToast() and throws outside a
   ToastProvider - so every render has to sit inside one, as it does in App. */
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

/* The primary button is "Next →" on step 1 of the upload path and "Create"
   everywhere else - the wizard gained a second screen for choosing tables. These
   tests are about the guards behind that button, not its label, so press
   whichever one is on screen. */
const create = () => {
  const next = screen.queryByRole("button", { name: /Next/ });
  fireEvent.click(next || screen.getByRole("button", { name: "Create" }));
};

/* The connection and the table tree share step 2, so anything about either has
   to advance past step 1 first. */
const goToTableStep = () => fireEvent.click(screen.getByRole("button", { name: /Next/ }));

/* The Mapping Workbook card is a Data Source option - a Flat File run (the
   default) is offered only the Profile Mapper Job card - so every workbook flow
   starts by choosing Data Source. */
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

    // The half that was missing entirely before: a map with nothing to run against.
    expect(await screen.findByText(/Select the saved connection/i)).toBeInTheDocument();
    expect(api.createDraftJob).not.toHaveBeenCalled();
  });
});

describe("the uploaded workbook", () => {
  it("shows which tables it contains, so the user knows what to pick", async () => {
    setup();
    await uploadWorkbook(["claim", "member"]);

    // Listed as one pill per table beside the "Found 2 tables" confirmation,
    // rather than the old comma-joined "Workbook tables: …" sentence.
    expect(screen.getByText("claim")).toBeInTheDocument();
    expect(screen.getByText("member")).toBeInTheDocument();
  });

  it("offers a connection picker only in upload mode", async () => {
    setup();

    // Mode "job" inherits the source job's connection server-side, so asking for
    // one there would be redundant.
    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();

    await uploadWorkbook();

    // It sits on step 2, beside the tree it is a view of - not on step 1.
    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();
    goToTableStep();
    expect(screen.getByText("Source Connection")).toBeInTheDocument();
  });

  it("loads the schemas of a picked connection", async () => {
    setup();
    await uploadWorkbook();
    goToTableStep();

    // SearchableSelect opens its dropdown on focus, not click.
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
  /**
   * The bug: `error` was one shared field. An inspect failure wrote its reason
   * there, then picking a connection cleared it - so the user was left with a
   * file visibly chosen in the input, no explanation, and a later "upload a
   * workbook first" that read as simply wrong.
   */
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

  /* There was a "survives picking a connection" case here. The connection
     picker now lives on step 2, and a rejected workbook fails validateStepOne,
     so a user in this state cannot reach the picker at all - the scenario is
     gone rather than merely untested. The separation it guarded (uploadError
     kept apart from the transient `error`) is still covered by the cases
     below. */

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
  /**
   * Picking an existing profile mapper run carries that run's tables with it, so
   * there is nothing left to choose and the job is created from the first
   * screen. Uploading a workbook does not: the tables it names still have to be
   * matched to real ones in a live connection, which is what step 2 is for.
   *
   * These assert the SHAPE of each path - which button commits, and that a step-1
   * problem is reported on step 1 - rather than driving the dropdowns, which the
   * guard tests above already cover.
   */
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
    // Still on step 1 - the Name field is hidden once step 2 is showing.
    expect(screen.getByLabelText("Name")).toBeVisible();
    expect(screen.getByRole("button", { name: /Next/ })).toBeInTheDocument();
  });
});

describe("stepping back and forward again", () => {
  /**
   * The bug: useCatalog holds its cache in useState, so it dies with
   * SchemaTreePicker - and the wizard unmounts that component on Back. Coming
   * forward again restored the ROWS (the parent holds those) but nothing
   * re-requested their columns, so columnsFor() reported "not loaded, no
   * error", which the Primary Key select renders as "Loading…". It span
   * forever, and the key the user had already chosen never came back because
   * its option list was empty.
   */
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

    // The selection survives, and its options are re-fetched rather than the
    // select being left in a permanent loading state.
    await waitFor(() => expect(screen.getByDisplayValue("claim_id")).toBeInTheDocument());
    expect(screen.queryByPlaceholderText("Loading…")).not.toBeInTheDocument();
  });
});

describe("arriving from a profile map's results page", () => {
  /**
   * The Run Validation button on ProfileMapperJob used to navigate to
   * /run/validator - the pre-V2 run page - which is why it showed a stale UI.
   * It now lands on the current Validator flow with that job pre-selected, so
   * the user is not asked to find in a dropdown the job they were just looking at.
   */
  it("pre-selects the source job and stays on the job mode", async () => {
    api.listJobs.mockResolvedValue({
      ok: true,
      data: { jobs: [{ job_id: "pm-7", name: "Claims Profile", status: "done" }] },
    });

    renderModal({ initialSourceJobId: "pm-7" });

    // Upload mode must not be selected - the connection picker belongs to it.
    expect(screen.queryByText("Source Connection")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Claims DQ" } });
    create();

    // With the source already chosen, Create must not complain about it.
    await waitFor(() =>
      expect(screen.queryByText(/Select a completed profile map/)).not.toBeInTheDocument()
    );
    await waitFor(() =>
      expect(api.createValidatorJobFromProfileMap).toHaveBeenCalledWith(
        "Claims DQ",
        "",
        "pm-7",
        // The optional LOV file, null when none was attached - the api helper
        // omits lov_file from the body entirely in that case.
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
  /**
   * A Flat File / Data Source pair above the source cards. Flat File (the
   * default) offers only the Profile Mapper Job card; the mapping-workbook card
   * is a Data Source option, since that path collects a database connection.
   */
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

    // Back on the job path: no workbook card or dropzone, and Create, not Next.
    expect(screen.queryByLabelText("Upload a mapping workbook")).not.toBeInTheDocument();
    expect(screen.queryByText("Upload mapping workbook")).not.toBeInTheDocument();
    expect(screen.getByLabelText("From a Profile Mapper job")).toBeChecked();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();

    pickDataSource();

    // The workbook choice was hidden, never overwritten.
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
