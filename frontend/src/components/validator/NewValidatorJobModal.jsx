/**
 * NewValidatorJobModal.jsx - "New Job" modal for the Validator page
 * (Validator.jsx).
 *
 * A validation run needs TWO things: a profile map (what to check) and a live
 * source connection (what to check it against). The two source modes differ only
 * in where those come from:
 *
 *   - "From a Profile Mapper job": pick a completed step-1 job and the backend
 *     (JobService.create_validator_draft) copies its params wholesale - connection,
 *     tables and all - and reads its profile-map rows fresh at start time, so
 *     later edits are picked up. The connection arrives for free, invisibly.
 *
 *   - "Upload a mapping workbook": the workbook supplies the map and nothing
 *     else. This mode used to stop there - it sent connection_id: null and a
 *     list of bare table-name STRINGS - so the job it created could never run:
 *     config_builder._build_tables calls table.get("name") on each entry and
 *     died with AttributeError, and with no connection there was no
 *     source.db/connection_string in the generated config either. It now
 *     collects a saved connection and real Schema/Table/Primary Key rows, the
 *     same way NewProfileMapperJobModal.jsx does, and converts them with the
 *     shared rowsToTables() so both pages put identical shapes on the wire.
 *
 * Reuse, not reinvention: SearchableSelect + useSavedConnections for the
 * connection, listConnectionSchemas for its schemas, and SchemaTreePicker
 * (+ useCatalog, which caches per level and coalesces in-flight requests) for
 * the rows. The third dropdown is relabelled "Primary Key" via columnLabel -
 * the profile mapper passes "CDE" there, since it is picking Critical Data
 * Elements; here the column feeds each table's primary_key.
 *
 * On the workbook's table names: after a successful inspect we seed one row per
 * table found, so the row count matches the work and the user is not clicking +
 * repeatedly, and we list the names above the grid so they know what to pick.
 * The table name is deliberately NOT pre-filled into the row. SchemaTreePicker
 * clears a row's Table whenever its Schema changes (correctly - the old table may
 * not exist in the new schema), so a pre-filled name would be wiped the moment the
 * user chose a schema, and the catalog needed to validate it lives inside that
 * component rather than here. Instead Create checks that every workbook table is
 * covered by a locked row and names the ones that are not, which is the part that
 * actually prevents a silently wrong job.
 *
 * A "Source type" radio (Flat File / Data Source) sits above the source cards
 * and decides which of them are offered: Flat File leaves only the Profile
 * Mapper Job card, because the workbook path collects a database connection and
 * tables and creates a "database" job. See `isUpload` for how the two combine.
 * The type itself is not sent to the API.
 *
 * The modal-box is a real <form> (onSubmit={handleCreate}, Create is
 * type="submit") - handleCreate calls e.preventDefault() first, since a real
 * <form> submit would otherwise navigate/reload the page. Enter-to-submit is
 * deliberately turned back off via onKeyDown={preventEnterSubmit} (helpers.js) -
 * Create is the only way to submit.
 *
 * On success it closes and calls onCreated() (Validator.jsx reloads its list -
 * the new "draft" row shows up right there) rather than navigating to
 * /validator/:jobId.
 *
 * ── Presentation ────────────────────────────────────────────────────────────
 * The chrome is styled by styles/new-job-modal.css, scoped under the `.njm`
 * class on the form; nothing below changes what is sent to the API. Three
 * choices there are load-bearing rather than cosmetic:
 *
 *   - The two source modes are cards (icon + title + description) whose radio
 *     is a real <input type="radio"> carrying an aria-label with the old,
 *     longer wording. The card is a <div role="radio"> with a click handler,
 *     NOT a <label> wrapping the input: a wrapping label would give the radio
 *     a second accessible name of "Mapping Workbook", which is also the file
 *     field's label, and getByLabelText("Mapping Workbook") would then be
 *     ambiguous. The click handler does what the label would have done.
 *
 *   - The file <input> is visually hidden (clip-path, not display:none, so it
 *     stays focusable and in the accessibility tree) and driven by the Browse
 *     Files button plus drag-and-drop on the dropzone. Both funnel into the
 *     one ingestFile() path, so a dropped file and a browsed file are
 *     inspected identically.
 *
 *   - Required markers are CSS ::after content, not label text, so each
 *     field's accessible name stays exactly what it was.
 */
import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Loader2,
  Table2,
  UploadCloud,
  X,
} from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import SearchableSelect from "../SearchableSelect.jsx";
import SchemaTreePicker, { EMPTY_ROW } from "../profileMapper/SchemaTreePicker.jsx";
import { useCompletedProfileMapJobs } from "../../hooks/useCompletedProfileMapJobs.js";
import { useSavedConnections } from "../../hooks/useSavedConnections.js";
import {
  createValidatorJobFromProfileMap,
  createDraftJob,
  inspectProfileMapWorkbook,
  listConnectionSchemas,
  updateJobTables,
} from "../../api/api.js";
import { preventEnterSubmit } from "../../utils/helpers.js";
import { SOURCE_TYPES } from "../../constants/sourceTypes.js";
import { rowsToTables } from "../../utils/profileMapperRows.js";
import ModalPortal from "../ModalPortal.jsx";
import LovUploadPanel from "../LovUploadPanel.jsx";
import "../../styles/new-job-modal.css";

/** Job names are shown untruncated in the jobs tables, so they are capped here
 *  rather than ellipsised there - the column is sized to fit this length. */
export const NAME_MAX_LENGTH = 32;

const NAME_PLACEHOLDER = "e.g. Orders DQ Validation - Sep 2026";
const DESCRIPTION_PLACEHOLDER = "Briefly describe what this validation run covers…";

/** Advisory only - the real limit is the server's. Stated in the dropzone so a
 *  rejection is not the first time the user hears about a ceiling. */
const MAX_UPLOAD_MB = 50;

/** Bytes -> the "248 KB" shown beside a picked file. Kept local: it is two
 *  lines and nothing else in the app formats file sizes yet. */
function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

/** The two kinds of source a run can read from, shown as the "Source type" radio.
 *  Values reuse SOURCE_TYPES so they line up with the source_type a Profile
 *  Mapper job already carries; the labels are this dialog's own ("Data Source",
 *  not SOURCE_LABELS' "Database Connection"). */
const SOURCE_TYPE_CHOICES = [
  { value: SOURCE_TYPES.FLAT_FILE, label: "Flat File" },
  { value: SOURCE_TYPES.DATABASE, label: "Data Source" },
];

const EMPTY_STATE = {
  name: "",
  description: "",
  /* Which kind of source the "Source type" radio has picked. It decides which
     source cards are offered (see isUpload) and is not sent to the API. */
  sourceType: SOURCE_TYPES.FLAT_FILE,
  /* 1 = identity and source; 2 = the connection, and which of its tables to
     validate with their primary keys. Only the "upload a workbook" path has a
     step 2: picking an existing profile mapper run already carries its
     connection AND its tables, so that path creates from step 1 and never sees
     a second screen. */
  step: 1,
  sourceMode: "job", // "job" or "upload"
  profileMapJobId: "",
  uploadedMapFilename: "",
  /* The one LOV file this job validates against - the server's stored name,
     same as uploadedMapFilename. Empty on every open: LOVs belong to the job
     they were uploaded for, so nothing carries over from an earlier one. */
  lovFile: "",
  /* What the user recognises - their own filename and its size. Distinct from
     uploadedMapFilename, which is the server's stored name and the only one
     that goes back over the wire. */
  pickedFileName: "",
  pickedFileSize: 0,
  uploadedTables: [],
  connectionId: "",
  schemas: null,
  rows: [{ ...EMPTY_ROW }],
  loadingSchemas: false,
  saving: false,
  error: "",
  // Kept separate from `error` on purpose. `error` is transient form feedback that
  // any later action may clear; whether the server accepted the workbook is
  // durable state that must survive picking a connection or toggling the mode.
  // Sharing one field meant choosing a connection wiped the upload's real failure
  // message, leaving only a later "upload a workbook first" - while the file input
  // still displayed the chosen filename, so the UI contradicted itself and the
  // actual reason was gone.
  uploadError: "",
  inspecting: false
};

export default function NewValidatorJobModal({
  open,
  onClose,
  onCreated,
  /** Pre-selects a completed Profile Mapper job. Set when the user arrives from
   *  that job's results page, so they are not asked to find in a dropdown the
   *  job they were just looking at. */
  initialSourceJobId = "",
}) {
  const [state, setState] = useState(EMPTY_STATE);
  /* Presentation-only, so not in `state`: whether a file is currently being
     dragged over the dropzone. */
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  // Applied when the modal opens, not on every render: the user must stay free
  // to change the selection afterwards.
  useEffect(() => {
    if (!open || !initialSourceJobId) return;
    setState((s) => ({ ...s, sourceMode: "job", profileMapJobId: initialSourceJobId }));
  }, [open, initialSourceJobId]);
  const { options: profileMapOptions, loading: loadingProfileMaps } = useCompletedProfileMapJobs(open);
  const { options: connectionOptions, loading: loadingConnections } = useSavedConnections(open);

  const isFlatFile = state.sourceType === SOURCE_TYPES.FLAT_FILE;

  /* The workbook path collects a database connection and tables and creates a
     "database" job, so it is a Data Source option and Flat File does not offer
     it. Derived from both fields rather than resetting sourceMode when Flat File
     is picked: the choice (and any workbook already uploaded) is still there if
     the user switches back, and there is no state in which the workbook section
     shows without its card. */
  const isUpload = state.sourceMode === "upload" && !isFlatFile;

  /* A run picked from the dropdown brings its own tables with it - there is
     nothing left to choose, so Create is offered straight away. */
  const hasTableStep = isUpload;
  const onTableStep = state.step === 2;

  /* The preconditions that belong to step 1 - identity and source. Shared with
     handleCreate rather than restated there: the "job" path submits from step 1,
     so the same checks have to run whether the user pressed Next or Create, and
     two copies would drift into two different messages for one problem.
     Step 2's own preconditions - the connection and the tables - live in
     validateStepTwo below, so a problem is always reported on the screen that
     can fix it. */
  function validateStepOne() {
    if (!state.name.trim()) return "Name is required";

    if (!isUpload) {
      return state.profileMapJobId ? "" : "Select a completed profile map";
    }

    if (!state.uploadedMapFilename) {
      // Distinguishes "you haven't picked a file" from "the file you picked was
      // rejected" - the file input shows a filename in both cases, so without
      // this the message looks wrong to anyone staring at a chosen file.
      return state.uploadError
        ? "This workbook was not accepted - see the error under Mapping Workbook. Fix it or choose another file."
        : "Choose a mapping workbook first";
    }

    return "";
  }

  /** Step 2, upload path only: the connection to read from, and the live tables
   *  behind the workbook's sheet names. */
  function validateStepTwo() {
    if (!state.connectionId) {
      return "Select the saved connection this profile map should be validated against";
    }

    if (!state.rows.some((row) => row.locked && row.schema && row.table)) {
      return "Select at least one table to validate";
    }

    const missing = uncoveredTables(state.rows, state.uploadedTables);
    if (missing.length) {
      return (
        `These tables are in the workbook but have no locked row: ${missing.join(", ")}. ` +
        `Add a row for each, or remove them from the workbook.`
      );
    }

    return "";
  }

  function goNext() {
    const error = validateStepOne();
    if (error) {
      setState((s) => ({ ...s, error }));
      return;
    }
    setState((s) => ({ ...s, step: 2, error: "" }));
  }

  function goBack() {
    setState((s) => ({ ...s, step: 1, error: "" }));
  }

  function handleClose() {
    setState(EMPTY_STATE);
    setDragging(false);
    onClose();
  }

  function pickMode(sourceMode) {
    setState((s) => ({ ...s, sourceMode, step: 1, error: "" }));
  }

  /** The single ingest path - the hidden input's onChange and the dropzone's
   *  onDrop both land here, so a dropped workbook is treated exactly like a
   *  browsed one instead of taking a second, subtly different route. */
  async function ingestFile(file) {
    if (!file) return;

    setState((s) => ({
      ...s,
      inspecting: true,
      error: "",
      uploadError: "",
      uploadedMapFilename: "",
      uploadedTables: [],
      pickedFileName: file.name,
      pickedFileSize: file.size || 0
    }));

    const result = await inspectProfileMapWorkbook(file);

    if (!result.ok) {
      // Stored as uploadError so it stays on screen until another file is picked.
      setState((s) => ({
        ...s,
        inspecting: false,
        uploadError: result.error || "The server could not read this workbook."
      }));
      return;
    }

    const tableNames = (result.data?.tables || []).map((t) => t.table_name);

    setState((s) => ({
      ...s,
      inspecting: false,
      uploadedMapFilename: result.data.filename,
      uploadedTables: tableNames,
      // One row per table the workbook describes, so the grid already has the
      // right shape. See the header comment for why the names aren't pre-filled.
      rows: tableNames.length
        ? tableNames.map(() => ({ ...EMPTY_ROW }))
        : [{ ...EMPTY_ROW }]
    }));
  }

  function handleFileChange(e) {
    ingestFile(e.target.files[0]);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    if (state.saving || state.inspecting) return;
    ingestFile(e.dataTransfer?.files?.[0]);
  }

  /** Clears the picked workbook and everything derived from it. The seeded rows
   *  go too: they exist only because that workbook named that many tables. */
  function clearFile() {
    if (fileInputRef.current) fileInputRef.current.value = "";
    setState((s) => ({
      ...s,
      uploadedMapFilename: "",
      pickedFileName: "",
      pickedFileSize: 0,
      uploadedTables: [],
      uploadError: "",
      error: "",
      rows: [{ ...EMPTY_ROW }]
    }));
  }

  /** One blank row per table the workbook names, so the grid opens at the right
   *  size. See the header comment for why the names are not pre-filled. */
  function seedRows() {
    return state.uploadedTables.length
      ? state.uploadedTables.map(() => ({ ...EMPTY_ROW }))
      : [{ ...EMPTY_ROW }];
  }

  async function handlePickConnection(connectionId) {
    if (!connectionId) {
      setState((s) => ({ ...s, connectionId: "", schemas: null, rows: seedRows() }));
      return;
    }

    // Rows are cleared on every change of connection, not just on clearing it.
    // A row names a schema and a table in the connection it was picked from;
    // carried into a different database those names are at best meaningless and
    // at worst silently valid, since `public`/`dbo` exist in most of them - so
    // the job would read the wrong table under a name that looked right.
    // Now that this picker sits on the same screen as the tree, switching
    // connections with tables already ticked is an ordinary thing to do rather
    // than something only reachable by going back a step.
    setState((s) => ({
      ...s,
      connectionId,
      schemas: null,
      error: "",
      loadingSchemas: true,
      rows: s.connectionId && s.connectionId !== connectionId ? seedRows() : s.rows
    }));

    const { ok, data, error } = await listConnectionSchemas(connectionId);

    if (!ok) {
      setState((s) => ({
        ...s,
        loadingSchemas: false,
        error: error || "Could not load schemas"
      }));
      return;
    }

    setState((s) => ({
      ...s,
      loadingSchemas: false,
      schemas: data?.schemas || []
    }));
  }

  /** Workbook tables with no locked row covering them - the silent-mismatch guard. */
  function uncoveredTables(rows, expected) {
    const picked = new Set(
      rows.filter((r) => r.locked && r.schema && r.table).map((r) => r.table.toLowerCase())
    );
    return expected.filter((name) => !picked.has(String(name).toLowerCase()));
  }

  async function handleCreate(e) {
    e.preventDefault(); // this is a real <form onSubmit>; without this the browser would navigate/reload on submit

    const name = state.name.trim();

    const stepOneError = validateStepOne();
    if (stepOneError) {
      // Send the user back to the screen the problem is on, rather than
      // reporting a missing connection over a table tree.
      setState((s) => ({ ...s, step: 1, error: stepOneError }));
      return;
    }

    if (isUpload) {
      const stepTwoError = validateStepTwo();
      if (stepTwoError) {
        setState((s) => ({ ...s, step: 2, error: stepTwoError }));
        return;
      }
    }

    setState((s) => ({ ...s, saving: true, error: "" }));

    let ok, error;
    if (!isUpload) {
      const res = await createValidatorJobFromProfileMap(
        name,
        state.description.trim(),
        state.profileMapJobId,
        state.lovFile || null
      );
      ok = res.ok;
      error = res.error;
    } else {
      const res = await createDraftJob(
        name,
        state.description.trim(),
        state.connectionId,
        "3",
        "database",
        state.uploadedMapFilename,
        null,
        state.lovFile || null
      );
      ok = res.ok;
      error = res.error;

      if (ok) {
        // Attached separately, exactly as the Profile Mapper does - rowsToTables
        // produces the {schema, name, primary_key} objects config_builder expects,
        // instead of the bare strings this modal used to send.
        const tables = rowsToTables(state.rows);
        if (tables.length) {
          const attached = await updateJobTables(res.data.job_id, tables);
          if (!attached.ok) {
            ok = false;
            error = attached.error || "The job was created but its tables could not be saved";
          }
        }
      }
    }

    if (!ok) {
      setState((s) => ({ ...s, saving: false, error: error || "Failed to create job" }));
      return;
    }

    handleClose();
    onCreated?.();
  }

  // Freeze the page behind the overlay - see the hook for why a plain
  // body overflow:hidden is not enough (nesting, scrollbar layout shift).
  useScrollLock(open);

  if (!open) return null;

  const tableCount = state.uploadedTables.length;

  return (
    <ModalPortal>
      <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && handleClose()}>
        <form
          className="njm modal-box wizard-box wizard-box-sm new-profile-mapper-job-modal-box"
          onSubmit={handleCreate}
          onKeyDown={preventEnterSubmit}
        >
          <div className="njm-header">
            <div className="njm-header-main">
              <span className="njm-header-icon" aria-hidden="true">
                <FileSearch size={20} />
              </span>
              <span>
                <span className="njm-title">
                  New Job{hasTableStep ? (onTableStep ? " – Select Tables" : " – Details") : ""}
                </span>
                <span className="njm-subtitle">
                  {onTableStep
                    ? "Match the workbook's tables to the connection and pick each primary key."
                    : "Create a new validation run from a profile map."}
                </span>
              </span>
            </div>
            <button type="button" className="njm-close" onClick={handleClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          {/* Direct child of .wizard-box, not of .wizard-body: the overlay is
              position:absolute against .wizard-box so it covers the footer's
              Create button too, rather than leaving it clickable mid-fetch. */}
          {state.loadingSchemas ? (
            <div className="wizard-loading-overlay">
              <span className="wizard-loading-spinner" aria-hidden="true" />
              <span className="hint">Loading schemas…</span>
            </div>
          ) : null}

          <div className="njm-body">
            <div className="njm-stack" hidden={onTableStep}>
              <div className="njm-field">
                <label className="njm-label is-required" htmlFor="val-job-name">Name</label>
                <input
                  id="val-job-name"
                  type="text"
                  maxLength={NAME_MAX_LENGTH}
                  placeholder={NAME_PLACEHOLDER}
                  value={state.name}
                  onChange={(e) => setState((s) => ({ ...s, name: e.target.value }))}
                />
                <span className="njm-count">
                  {state.name.length}/{NAME_MAX_LENGTH}
                </span>
              </div>

              <div className="njm-field">
                <label className="njm-label" htmlFor="val-job-desc">Description</label>
                <textarea
                  id="val-job-desc"
                  maxLength={200}
                  placeholder={DESCRIPTION_PLACEHOLDER}
                  value={state.description}
                  onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                />
                <span className="njm-count">{state.description.length}/200</span>
              </div>

              <div className="njm-field">
                <span className="njm-label">Source type</span>
                {/* A plain <label> around each input, unlike the source cards
                    below: the text is two short words, so it makes a clean
                    accessible name and none of the card workarounds apply. */}
                <div className="njm-radio-row" role="radiogroup" aria-label="Source type">
                  {SOURCE_TYPE_CHOICES.map((opt) => (
                    <label key={opt.value} className="njm-radio-option">
                      <input
                        type="radio"
                        name="sourceType"
                        value={opt.value}
                        checked={state.sourceType === opt.value}
                        onChange={() => setState((s) => ({ ...s, sourceType: opt.value, error: "" }))}
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="njm-field">
                <span className="njm-label is-required">Choose a source</span>
                {/* radiogroup + role="radio" on the cards: the clickable surface
                    is the whole card, so it has to announce itself as the option
                    rather than as a plain box that happens to contain a radio. */}
                <div className="njm-source-grid" role="radiogroup" aria-label="Choose a source">
                  <div
                    role="radio"
                    aria-checked={!isUpload}
                    className={`njm-source-card${!isUpload ? " is-selected" : ""}`}
                    onClick={() => pickMode("job")}
                  >
                    {/* A profile map is the rulebook a profiling run produced
                        and an analyst then reviewed and saved - a checked-off
                        list of rules per column. The database cylinder that was
                        here said "a database", which is the one thing this
                        option is NOT: the connection comes with the job, it is
                        not what you are picking. */}
                    <span className="njm-source-icon" aria-hidden="true">
                      <ClipboardCheck size={20} />
                    </span>
                    <span className="njm-source-text">
                      <span className="njm-source-title">Profile Mapper Job</span>
                      <span className="njm-source-desc">
                        Select from an existing profile mapper job
                      </span>
                    </span>
                    {/* aria-label keeps the original, fuller wording as this
                        radio's accessible name - the visible title is only two
                        words and would not stand alone out of context. */}
                    <input
                      className="njm-source-radio"
                      type="radio"
                      name="sourceMode"
                      value="job"
                      aria-label="From a Profile Mapper job"
                      checked={!isUpload}
                      onChange={(e) => pickMode(e.target.value)}
                    />
                  </div>

                  {/* Data Source only - Flat File is left with the card above. */}
                  {!isFlatFile ? (
                    <div
                      role="radio"
                      aria-checked={isUpload}
                      className={`njm-source-card${isUpload ? " is-selected" : ""}`}
                      onClick={() => pickMode("upload")}
                    >
                      <span className="njm-source-icon" aria-hidden="true">
                        <FileText size={20} />
                      </span>
                      <span className="njm-source-text">
                        <span className="njm-source-title">Mapping Workbook</span>
                        <span className="njm-source-desc">
                          Upload an Excel workbook to map and validate
                        </span>
                      </span>
                      <input
                        className="njm-source-radio"
                        type="radio"
                        name="sourceMode"
                        value="upload"
                        aria-label="Upload a mapping workbook"
                        checked={isUpload}
                        onChange={(e) => pickMode(e.target.value)}
                      />
                    </div>
                  ) : null}
                </div>
              </div>

              {!isUpload ? (
                <div className="njm-field">
                  {/* No htmlFor: SearchableSelect owns its own input and takes no id. */}
                  <span className="njm-label is-required">Select profile map</span>
                  <SearchableSelect
                    value={state.profileMapJobId}
                    options={profileMapOptions}
                    onChange={(v) => setState((s) => ({ ...s, profileMapJobId: v }))}
                    placeholder={loadingProfileMaps ? "Loading profile maps…" : "Search completed profile maps…"}
                    emptyLabel={loadingProfileMaps ? "Loading…" : "No completed jobs available."}
                    disabled={state.saving}
                  />
                  <span className="njm-hint">
                    Its connection and tables are inherited by this validation run.
                  </span>
                </div>
              ) : (
                <>
                  <div className="njm-field">
                    {/* The visible text is the instruction; the input's own
                        aria-label stays "Mapping Workbook" so nothing that
                        queried it by that name has to change. */}
                    <label className="njm-label is-required" htmlFor="val-job-upload">
                      Upload mapping workbook
                    </label>

                    <div
                      className={
                        "njm-dropzone" +
                        (dragging ? " is-dragging" : "") +
                        (state.inspecting ? " is-busy" : "")
                      }
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragging(true);
                      }}
                      onDragLeave={() => setDragging(false)}
                      onDrop={handleDrop}
                    >
                      <span className="njm-dropzone-icon" aria-hidden="true">
                        {state.inspecting ? (
                          <Loader2 size={22} className="njm-spin" />
                        ) : (
                          <UploadCloud size={22} />
                        )}
                      </span>
                      <span className="njm-dropzone-text">
                        <span className="njm-dropzone-title">
                          {state.inspecting ? "Reading workbook…" : "Choose a file or drag and drop"}
                        </span>
                        <span className="njm-dropzone-sub">
                          Supports .xlsx files (max {MAX_UPLOAD_MB} MB)
                        </span>
                      </span>
                      <input
                        id="val-job-upload"
                        ref={fileInputRef}
                        className="njm-file-input"
                        type="file"
                        accept=".xlsx"
                        aria-label="Mapping Workbook"
                        onChange={handleFileChange}
                        disabled={state.saving || state.inspecting}
                      />
                      <button
                        type="button"
                        className="btn btn-sm njm-browse"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={state.saving || state.inspecting}
                      >
                        Browse Files
                      </button>
                    </div>

                    {state.pickedFileName ? (
                      <div className="njm-file-row">
                        <span className="njm-file-icon" aria-hidden="true">
                          <FileSpreadsheet size={18} />
                        </span>
                        <span className="njm-file-meta">
                          <span className="njm-file-name">{state.pickedFileName}</span>
                          <span className="njm-file-size">
                            {state.inspecting
                              ? "Inspecting…"
                              : formatBytes(state.pickedFileSize)}
                          </span>
                        </span>
                        {state.uploadedMapFilename && !state.inspecting ? (
                          <span className="njm-file-ok" aria-hidden="true">
                            <CheckCircle2 size={18} />
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="njm-file-remove"
                          onClick={clearFile}
                          disabled={state.saving || state.inspecting}
                          aria-label="Remove file"
                        >
                          <X size={15} aria-hidden="true" />
                        </button>
                      </div>
                    ) : null}

                    {state.uploadedMapFilename && !state.inspecting ? (
                      <div className="njm-found">
                        <span className="njm-found-icon" aria-hidden="true">
                          <CheckCircle2 size={17} />
                        </span>
                        <span>
                          <span className="njm-found-title">
                            {`Found ${tableCount} ${tableCount === 1 ? "table" : "tables"} in the workbook`}
                          </span>
                          {tableCount ? (
                            <span className="njm-pills">
                              {state.uploadedTables.map((name) => (
                                <span className="njm-pill" key={name}>{name}</span>
                              ))}
                            </span>
                          ) : null}
                        </span>
                      </div>
                    ) : null}

                    {/* Sits with the field it belongs to, and survives every later
                        action, so the reason a workbook was refused cannot vanish
                        behind an unrelated click. */}
                    {state.uploadError && !state.inspecting && (
                      <div className="njm-alert" role="alert">
                        <AlertTriangle size={16} aria-hidden="true" />
                        <span>{state.uploadError}</span>
                      </div>
                    )}
                  </div>

                </>
              )}

              {/* The one LOV file this job validates against - optional, and
                  only used by DQ8 rules. Scoped to this job: nothing uploaded
                  for an earlier job is offered here. */}
              <LovUploadPanel
                compact
                className="njm-lov-section"
                value={state.lovFile || null}
                onChange={(filename) =>
                  setState((s) => ({ ...s, lovFile: filename || "" }))
                }
              />
            </div>

            {/* Step 2, upload path only. Rendered only while it is on screen, so
                the tree is not walking a catalog behind a hidden pane.

                The connection lives here rather than on step 1 because it is
                what the tree below is a view OF: picking a database and then
                browsing it are one task, and splitting them across two screens
                meant changing your mind about the connection was a Back, a
                re-pick and a Next. */}
            {onTableStep ? (
              <div className="njm-stack">
                {tableCount > 0 ? (
                  /* The workbook names the tables it expects; uncoveredTables()
                     rejects a job that misses one, so showing them here is what
                     makes that check followable rather than a surprise. */
                  <div>
                    <div className="njm-step2-lead">
                      <Table2 size={15} aria-hidden="true" />
                      <span>Match each workbook table to a table in the connection</span>
                    </div>
                    <div className="njm-pills">
                      {state.uploadedTables.map((name) => (
                        <span className="njm-pill is-neutral" key={name}>{name}</span>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="njm-field">
                  {/* No htmlFor: SearchableSelect owns its own input and takes no
                      id, so a htmlFor here would point at nothing. Same as the
                      profile mapper's connection field. */}
                  <span className="njm-label is-required">Source Connection</span>
                  <div className="njm-select-wrap">
                    <span className="njm-select-icon" aria-hidden="true">
                      <Database size={15} />
                    </span>
                    <SearchableSelect
                      value={state.connectionId}
                      options={connectionOptions}
                      onChange={handlePickConnection}
                      placeholder={loadingConnections ? "Loading saved connections…" : "Search saved connections…"}
                      emptyLabel={loadingConnections ? "Loading…" : "No saved connections yet"}
                      disabled={state.saving || state.loadingSchemas}
                    />
                  </div>
                  <span className="njm-hint">
                    The database this profile map will be validated against.
                  </span>
                </div>

                {state.connectionId && state.schemas && !state.loadingSchemas ? (
                  <SchemaTreePicker
                    rows={state.rows}
                    onChange={(rows) => setState((s) => ({ ...s, rows }))}
                    connectionId={state.connectionId}
                    schemas={state.schemas}
                    columnLabel="Primary Key"
                  />
                ) : !state.connectionId ? (
                  <p className="njm-waiting">
                    Choose a source connection to browse its schemas and tables.
                  </p>
                ) : null}
              </div>
            ) : null}

            {state.error ? (
              <div className="njm-alert" role="alert">
                <AlertTriangle size={16} aria-hidden="true" />
                <span>{state.error}</span>
              </div>
            ) : null}
          </div>

          <div className="njm-footer">
            {onTableStep ? (
              <button type="button" className="btn btn-ghost" onClick={goBack} disabled={state.saving}>
                <ArrowLeft size={15} aria-hidden="true" />
                Back
              </button>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={handleClose} disabled={state.saving}>
                Cancel
              </button>
            )}

            {hasTableStep && !onTableStep ? (
              /* type="button" so Enter and this click both advance rather than
                 submitting a job whose tables have not been chosen yet. */
              <button
                key="btn-next"
                type="button"
                className="btn btn-primary"
                onClick={goNext}
                disabled={state.inspecting}
              >
                Next
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button key="btn-create" type="submit" className="btn btn-primary" disabled={state.saving}>
                {state.saving ? <Loader2 size={15} className="njm-spin" aria-hidden="true" /> : null}
                {state.saving ? "Creating…" : "Create"}
              </button>
            )}
          </div>
        </form>
      </div>
    </ModalPortal>
  );
}
