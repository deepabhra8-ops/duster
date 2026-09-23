/**
 * NewProfileMapperJobModal.jsx - "New Job" modal for the Profile Mapper
 * page (ProfileMapper.jsx).
 *
 * Step 1 is the job's identity and which KIND of source it has: Name,
 * Description, and a Source Type radio (Flat File / Database,
 * `SOURCE_TYPE_OPTIONS`) rendered as two cards. What follows depends on that
 * choice:
 *
 *   - Flat File: a drag-and-drop/Browse-Files dropzone, inline on step 1 -
 *     the files ARE the source, so there is nothing to pick on a second
 *     screen and Create is offered straight away. It takes one or more CSVs,
 *     each becoming its own table (and its own results tab on
 *     ProfileMapperJob.jsx), named after the file minus ".csv". Picking only
 *     collects Files client-side (`flatFiles` state); the actual uploads
 *     happen after Create returns a real job id (see below). A file whose
 *     table name matches one already picked (ignoring case) is refused -
 *     the profiling engine keys results by table name, so it would overwrite.
 *
 *   - Database: step 2, which carries BOTH the saved-connection picker
 *     (SearchableSelect + useSavedConnections, same as
 *     NewValidatorJobModal.jsx) and the SchemaTreePicker it feeds. They sit
 *     together because the tree is a view OF the connection: with the picker
 *     on step 1 instead, changing your mind about the connection cost a Back,
 *     a re-pick and a Next. Picking one loads just the connection's schema
 *     names (listConnectionSchemas - GET /api/connections/{id}/metadata); if
 *     ConnectionWizardModal.jsx's "Save & Connect" (or any earlier scan)
 *     already cached one, it loads instantly, no spinner. Only when nothing
 *     is cached does it fall back to a live scan - `loadingSchemas` shows a
 *     circular spinner covering the whole modal (.wizard-loading-overlay)
 *     while that is in flight, the same visual weight as a blocking action.
 *     Tables and columns then load per selection inside the picker, cached
 *     per level by useCatalog. The tree's third column is relabelled "CDE"
 *     via the columnLabel prop (SchemaTreePicker.jsx's own doc comment)
 *     rather than the generic "Column" ProfileMapperJob.jsx uses, since here
 *     it is picking Critical Data Elements per table.
 *
 * Presentation comes from styles/new-job-modal.css, scoped under the `njm`
 * class on the form and shared with NewValidatorJobModal.jsx - the two New Job
 * wizards are the same dialog shape doing different jobs, so they use one
 * stylesheet rather than drifting into two lookalikes. Nothing in that styling
 * changes what is sent to the API. Two details there are load-bearing rather
 * than cosmetic, and both match the Validator's wizard: each source card is a
 * <div role="radio"> wrapping a real <input type="radio"> rather than a
 * <label> (a wrapping label would make the card's whole three-line text the
 * radio's accessible name), and the file <input> is visually hidden with
 * clip-path rather than display:none, so it stays focusable and in the
 * accessibility tree while Browse Files and drag-and-drop drive it.
 *
 * There is deliberately no "also run DQ Validator" checkbox here. One existed
 * as pure UI state - never sent to POST /api/jobs/draft, never acted on - which
 * silently did nothing when ticked. Chaining a validator onto a profile mapper
 * run needs a completion hook that doesn't exist yet; until it does, the
 * supported path is the Validator page, which creates a job from a completed
 * Profile Mapper job (POST /api/jobs/validator-draft) and picks up any
 * profile-map edits made in the meantime.
 *
 * Create first guards Database jobs client-side: at least one row must be
 * locked with a Schema, Table, and CDE column all picked (same "locked"
 * flag SchemaTreePicker.jsx sets on every table the user ticks), otherwise it's rejected
 * with a toast rather than reaching the backend at all - mirrors the
 * "Add at least one source table" guard the Flat File side already gets
 * for free from config_builder.py's validate(), which a Database job never
 * hits itself since its tables are attached via PATCH .../tables, not
 * POST /api/run.
 *
 * Create calls the real POST /api/jobs/draft (see docs/ux-plan.md §5's
 * "Live backend wiring" note) with the chosen source_type and, for
 * Database, the picked connection_id - creates a job in "draft" status,
 * then:
 *   - Database: PATCH /api/job/{id}/tables (updateJobTables) with the
 *     locked rows converted via rowsToTables (profileMapperRows.js -
 *     shared with ProfileMapperJob.jsx, factored out for exactly this).
 *   - Flat File: one upload per picked file, one after another -
 *     POST /api/upload (uploadFile, kind "data"), the shared Data uploads
 *     directory config_builder.py's CSV source resolves against - then a
 *     single PATCH /api/job/{id}/tables (updateJobTables) with one table
 *     entry per successful upload (`file`) so the draft has something to run.
 *     Without this table step a flat-file draft would fail validation with
 *     "Add at least one source table" the moment Run was clicked. A file that
 *     fails to upload is left out and named in a warning toast; the job keeps
 *     the rest.
 *
 *     (A per-job source-copy endpoint, POST /api/job/{id}/source, briefly
 *     existed to isolate a job's source data from the shared directory -
 *     removed along with the side-rail uploads list it was feeding.)
 * Either way it then closes and calls `onCreated` (ProfileMapper.jsx resets
 * to page 1 and reloads its list - see that page's own header comment)
 * rather than navigating to the new job's page - the new job shows up
 * right there in the table instead of jumping the user away from it.
 *
 * The modal-box itself is a real <form> now (onSubmit={handleCreate},
 * Create is type="submit") rather than a plain div - handleCreate takes
 * the submit event and calls e.preventDefault() first, since a real <form>
 * submit would otherwise navigate/reload the page. Enter-to-submit (the
 * implicit behavior a real <form> gets from any single-line text input,
 * e.g. Name or Select Saved Connection's search box) is deliberately
 * turned back off via onKeyDown={preventEnterSubmit} (helpers.js) - per
 * request, Create is the only way to submit. The close ✕ stays
 * type="button" so it can't accidentally trigger a submit itself.
 *
 * The wizard-box-sm / new-profile-mapper-job-modal-box sizing classes are still
 * on the form, but `.njm` overrides both: the dialog is 660px wide with an auto
 * height capped at 88vh, so it grows and shrinks with the chosen source type
 * rather than being clipped by a fixed 520/640px. The classes stay because the
 * loading overlay positions against .wizard-box.
 */
import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import SearchableSelect from "../SearchableSelect.jsx";
import SchemaTreePicker, { EMPTY_ROW } from "./SchemaTreePicker.jsx";
import {
  createDraftJob,
  listConnectionSchemas,
  updateJobTables,
  uploadFile,
} from "../../api/api.js";
import { useSavedConnections } from "../../hooks/useSavedConnections.js";
import { useToast } from "../../hooks/useToast.js";
import { preventEnterSubmit } from "../../utils/helpers.js";
import { SOURCE_TYPES, SOURCE_TYPE_OPTIONS } from "../../constants/sourceTypes.js";
import { rowsToTables } from "../../utils/profileMapperRows.js";
import ModalPortal from "../ModalPortal.jsx";
import "../../styles/new-job-modal.css";

/** Job names are shown untruncated in the jobs tables, so they are capped here
 *  rather than ellipsised there - the column is sized to fit this length. */
export const NAME_MAX_LENGTH = 32;

const NAME_PLACEHOLDER = "e.g. Customer Master Profile - Sep 2026";
const DESCRIPTION_PLACEHOLDER = "Briefly describe what this profiling job covers…";
const MAX_CSV_BYTES = 200 * 1024 * 1024; // matches MAX_UPLOAD_BYTES (appConfig.js) for the app's other CSV uploads
const MAX_CSV_MB = MAX_CSV_BYTES / (1024 * 1024);

/** Card copy for the two source types. Keyed off SOURCE_TYPES so the labels in
 *  constants/sourceTypes.js stay the single source of truth for the NAMES -
 *  only the supporting lines and the icon live here, since those are this
 *  dialog's presentation rather than a shared domain fact. */
const SOURCE_CARD_DETAIL = {
  [SOURCE_TYPES.FLAT_FILE]: {
    Icon: FileText,
    description: "Upload files from your system",
    note: "Supports one or more .csv files",
  },
  [SOURCE_TYPES.DATABASE]: {
    Icon: Database,
    description: "Use an existing database connection",
    note: "Connect to validate and profile your data",
  },
};

/** A flat file's table name - also its tab label on the results page. */
const tableNameFor = (file) => file.name.replace(/\.csv$/i, "");

/** First name that appears twice, ignoring case, or "". */
function findDuplicateName(names) {
  const seen = new Set();
  for (const name of names) {
    const key = name.toLowerCase();
    if (seen.has(key)) return name;
    seen.add(key);
  }
  return "";
}

/** Bytes -> the "248 KB" shown beside a picked file. */
function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const EMPTY_STATE = {
  /* 1 = the job's identity and its source; 2 = which tables to profile.
     Splitting them keeps the first screen to four short fields and gives the
     tree the whole dialog, instead of one column that scrolled past the Create
     button before the user had chosen anything. */
  step: 1,
  name: "",
  description: "",
  sourceType: SOURCE_TYPES.FLAT_FILE,
  connectionId: "",
  schemas: null,
  rows: [{ ...EMPTY_ROW }],
  loadingSchemas: false,
  flatFiles: [],
  dragOver: false,
  error: "",
  saving: false,
  /* { current, total } while flat files upload after Create, else null. */
  uploading: null,
};

export default function NewProfileMapperJobModal({ open, onClose, onCreated }) {
  const { showToast } = useToast();
  const [state, setState] = useState(EMPTY_STATE);
  const { options: connectionOptions, loading: loadingConnections } = useSavedConnections(open);
  const flatFileInputRef = useRef(null);

  const isDatabase = state.sourceType === SOURCE_TYPES.DATABASE;

  /* A flat-file job has nothing to pick on a second screen - the file IS the
     source - so it is created from step 1. Only a database job has tables. */
  const hasTableStep = isDatabase;
  const onTableStep = state.step === 2;

  /* Step 1 is identity and which KIND of source this is. The connection itself
     belongs to step 2, beside the schema tree it is a view of - see the render
     below - so it is deliberately not checked here; handleCreate still guards
     it, and that guard is only reachable from step 2. */
  function validateStepOne() {
    if (!state.name.trim()) return "Name is required";
    if (!isDatabase && state.flatFiles.length === 0) return "Choose at least one CSV file";
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
    onClose();
  }

  async function handlePickConnection(connectionId) {
    if (!connectionId) {
      setState((s) => ({ ...s, connectionId: "", schemas: null, rows: [{ ...EMPTY_ROW }] }));
      return;
    }

    // Only the schema names are read here - they are already stored against the
    // connection, so this is a fast lookup rather than a catalog walk. Tables and
    // columns load per selection inside the picker.
    setState((s) => ({ ...s, connectionId, schemas: null, error: "", loadingSchemas: true }));

    const { ok, data, error } = await listConnectionSchemas(connectionId);

    if (!ok) {
      setState((s) => ({
        ...s,
        loadingSchemas: false,
        error: error || "Could not load schemas",
      }));
      return;
    }

    setState((s) => ({
      ...s,
      loadingSchemas: false,
      schemas: data?.schemas || [],
      rows: [{ ...EMPTY_ROW }],
    }));
  }

  /** Adds the valid files to the list and reports each one it refused, so one bad
   *  file in a multi-select doesn't cost the user the rest of the selection. */
  function handleFlatFilesPicked(fileList) {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;

    setState((s) => {
      const accepted = [...s.flatFiles];
      const problems = [];

      for (const file of files) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
          problems.push(`"${file.name}" is not a .csv file.`);
        } else if (file.size > MAX_CSV_BYTES) {
          problems.push(`"${file.name}" exceeds the ${MAX_CSV_MB} MB limit.`);
        } else if (findDuplicateName([...accepted.map(tableNameFor), tableNameFor(file)])) {
          problems.push(`A file named "${file.name}" is already added.`);
        } else {
          accepted.push(file);
        }
      }

      return { ...s, flatFiles: accepted, error: problems.join(" ") };
    });
  }

  function handleRemoveFlatFile(file) {
    setState((s) => ({ ...s, flatFiles: s.flatFiles.filter((f) => f !== file), error: "" }));
  }

  /** Upload each file in turn, then attach every one that made it as the job's
   *  tables in a single PATCH. Sequential rather than parallel: each file can be
   *  200 MB, and "Uploading 2 of 5" tells the user where it is. */
  async function attachFlatFiles(jobId, jobName) {
    const total = state.flatFiles.length;
    const tables = [];
    const failed = [];

    for (const [index, file] of state.flatFiles.entries()) {
      setState((s) => ({ ...s, uploading: { current: index + 1, total } }));
      const uploaded = await uploadFile(file, "data");
      if (uploaded.ok) {
        tables.push({ name: tableNameFor(file), file: uploaded.data?.filename || file.name, primary_key: "" });
      } else {
        failed.push(`"${file.name}" (${uploaded.error || "unknown error"})`);
      }
    }

    if (tables.length) {
      const attached = await updateJobTables(jobId, tables);
      if (!attached.ok) {
        showToast({
          type: "warn",
          title: "Job created, but files weren't attached",
          message:
            `"${jobName}" was created, but its files couldn't be attached ` +
            `(${attached.error || "unknown error"}). Reattach them before running this job.`,
        });
        return;
      }
    }

    if (failed.length === total) {
      showToast({
        type: "warn",
        title: "Job created, but files weren't attached",
        message:
          `"${jobName}" was created, but none of its files could be uploaded: ` +
          `${failed.join(", ")}. Reattach them before running this job.`,
      });
    } else if (failed.length) {
      showToast({
        type: "warn",
        title: `${failed.length} of ${total} files weren't uploaded`,
        message:
          `"${jobName}" was created with ${tables.length} of ${total} files. ` +
          `These couldn't be uploaded: ${failed.join(", ")}.`,
      });
    }
  }

  /** Why the ticked database tables can't be created as a job, or null. */
  function databaseSelectionProblem() {
    if (!state.rows.some((row) => row.locked && row.schema && row.table && row.column)) {
      return {
        title: "No table selected",
        message: "Tick at least one table and give it a CDE column before creating this job.",
      };
    }
    // The backend refuses two tables with one name (results are keyed by name),
    // e.g. the same table ticked in two schemas - catch it before a job exists.
    const duplicate = findDuplicateName(rowsToTables(state.rows).map((t) => t.name));
    if (duplicate) {
      return {
        title: "Duplicate table name",
        message: `More than one selected table is named "${duplicate}". Keep only one of them.`,
      };
    }
    return null;
  }

  async function handleCreate(e) {
    e.preventDefault(); // this is now a real <form onSubmit>; without this the browser would navigate/reload on submit
    const name = state.name.trim();
    const stepOneError = validateStepOne();
    if (stepOneError) {
      setState((s) => ({ ...s, error: stepOneError }));
      return;
    }
    if (isDatabase && !state.connectionId) {
      // Reported on the screen that can fix it, now that the picker lives there.
      setState((s) => ({ ...s, step: 2, error: "Select a saved connection" }));
      return;
    }
    const selectionProblem = isDatabase ? databaseSelectionProblem() : null;
    if (selectionProblem) {
      showToast({ type: "error", ...selectionProblem });
      return;
    }

    setState((s) => ({ ...s, saving: true, error: "" }));
    const { ok, data, error } = await createDraftJob(
      name,
      state.description.trim(),
      isDatabase ? state.connectionId : "",
      "1",
      state.sourceType
    );
    if (!ok) {
      setState((s) => ({ ...s, saving: false, error: error || "Failed to create job" }));
      return;
    }

    const jobId = data.job_id;
    if (isDatabase) {
      const tables = rowsToTables(state.rows);
      if (tables.length) await updateJobTables(jobId, tables);
    } else if (state.flatFiles.length) {
      // Global "data" uploads are what config_builder.py's CSV source reads
      // from (job_source_service.py, the job-owned-copy alternative, was
      // removed) - register each as one of this draft's tables so Run works.
      await attachFlatFiles(jobId, name);
    }

    handleClose();
    onCreated?.();
  }

  // Freeze the page behind the overlay - see the hook for why a plain
  // body overflow:hidden is not enough (nesting, scrollbar layout shift).
  useScrollLock(open);

  if (!open) return null;

  let createLabel = "Create";
  if (state.uploading) createLabel = `Uploading ${state.uploading.current} of ${state.uploading.total}…`;
  else if (state.saving) createLabel = "Creating…";

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
                  New Job{hasTableStep ? (onTableStep ? " - Select Tables" : " - Details") : ""}
                </span>
                <span className="njm-subtitle">
                  {onTableStep
                    ? "Pick the tables to profile and the CDE column for each."
                    : "Create a new profiling job with your data source details."}
                </span>
              </span>
            </div>
            <button type="button" className="njm-close" onClick={handleClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          {/* Direct child of .wizard-box, not of the body: position:absolute
              against the box covers the footer's Create button too, rather than
              leaving it clickable mid-fetch. */}
          {state.loadingSchemas ? (
            <div className="wizard-loading-overlay">
              <span className="wizard-loading-spinner" aria-hidden="true" />
              <span className="hint">Loading schemas…</span>
            </div>
          ) : null}

          <div className="njm-body">
            <div className="njm-stack" hidden={onTableStep}>
              <div className="njm-field">
                <label className="njm-label is-required" htmlFor="pm-job-name">Name</label>
                <input
                  id="pm-job-name"
                  type="text"
                  maxLength={NAME_MAX_LENGTH}
                  placeholder={NAME_PLACEHOLDER}
                  value={state.name}
                  onChange={(e) => setState((s) => ({ ...s, name: e.target.value }))}
                />
                <span className="njm-field-foot">
                  <span className="njm-hint">Give a unique and meaningful name for this job.</span>
                  <span className="njm-count">
                    {state.name.length}/{NAME_MAX_LENGTH}
                  </span>
                </span>
              </div>

              <div className="njm-field">
                <label className="njm-label" htmlFor="pm-job-desc">Description</label>
                <textarea
                  id="pm-job-desc"
                  maxLength={200}
                  placeholder={DESCRIPTION_PLACEHOLDER}
                  value={state.description}
                  onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                />
                <span className="njm-field-foot">
                  <span className="njm-hint">This will help you identify the purpose of the job later.</span>
                  <span className="njm-count">{state.description.length}/200</span>
                </span>
              </div>

              <div className="njm-field">
                <span className="njm-label is-required">Source Type</span>
                {/* Cards rather than bare radios, and each card is a
                    <div role="radio"> with a click handler rather than a
                    <label> wrapping its input: a wrapping label would make the
                    card's whole text the radio's accessible name, which reads
                    as one long run-on. The input keeps the short label from
                    constants/sourceTypes.js instead. */}
                <div className="njm-source-grid" role="radiogroup" aria-label="Source type">
                  {SOURCE_TYPE_OPTIONS.map((opt) => {
                    const detail = SOURCE_CARD_DETAIL[opt.value];
                    const Icon = detail.Icon;
                    const isPicked = state.sourceType === opt.value;

                    return (
                      <div
                        key={opt.value}
                        role="radio"
                        aria-checked={isPicked}
                        className={`njm-source-card${isPicked ? " is-selected" : ""}`}
                        onClick={() => setState((s) => ({ ...s, sourceType: opt.value, step: 1, error: "" }))}
                      >
                        <span className="njm-source-icon" aria-hidden="true">
                          <Icon size={20} />
                        </span>
                        <input
                          className="njm-source-radio"
                          type="radio"
                          name="pm-job-source-type"
                          value={opt.value}
                          aria-label={opt.label}
                          checked={isPicked}
                          onChange={() => setState((s) => ({ ...s, sourceType: opt.value, step: 1, error: "" }))}
                        />
                        <span className="njm-source-text">
                          <span className="njm-source-title">{opt.label}</span>
                          <span className="njm-source-desc">{detail.description}</span>
                          <span className="njm-source-note">{detail.note}</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {isDatabase ? (
                <p className="njm-hint">
                  You will choose the connection and its tables on the next screen.
                </p>
              ) : (
                <div className="njm-field">
                  <span className="njm-label is-required">Data Files</span>

                  {/* Same dropzone as the Validator's workbook upload - one
                      pattern for "give me a file" across both wizards. The real
                      <input> is visually hidden (clip-path, not display:none, so
                      it stays focusable and in the accessibility tree) and driven
                      by Browse Files and by drops, both of which funnel into the
                      one handleFlatFilesPicked path that enforces .csv, the size
                      cap and unique names. Picking again adds to the list. */}
                  <div
                    className={`njm-dropzone${state.dragOver ? " is-dragging" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setState((s) => ({ ...s, dragOver: true }));
                    }}
                    onDragLeave={() => setState((s) => ({ ...s, dragOver: false }))}
                    onDrop={(e) => {
                      e.preventDefault();
                      setState((s) => ({ ...s, dragOver: false }));
                      handleFlatFilesPicked(e.dataTransfer.files);
                    }}
                  >
                    <span className="njm-dropzone-icon" aria-hidden="true">
                      <UploadCloud size={22} />
                    </span>
                    <span className="njm-dropzone-text">
                      <span className="njm-dropzone-title">Choose files or drag and drop</span>
                      <span className="njm-dropzone-sub">
                        One or more .csv files (max {MAX_CSV_MB} MB each)
                      </span>
                    </span>
                    <input
                      ref={flatFileInputRef}
                      className="njm-file-input"
                      type="file"
                      accept=".csv"
                      multiple
                      aria-label="Data Files"
                      onChange={(e) => {
                        handleFlatFilesPicked(e.target.files);
                        e.target.value = "";
                      }}
                    />
                    <button
                      type="button"
                      className="btn btn-sm njm-browse"
                      onClick={() => flatFileInputRef.current?.click()}
                      disabled={state.saving}
                    >
                      Browse Files
                    </button>
                  </div>

                  {state.flatFiles.map((file) => (
                    <div className="njm-file-row" key={file.name}>
                      <span className="njm-file-icon" aria-hidden="true">
                        <FileSpreadsheet size={18} />
                      </span>
                      <span className="njm-file-meta">
                        <span className="njm-file-name">{file.name}</span>
                        <span className="njm-file-size">
                          {formatBytes(file.size)} · uploaded once this job is created
                        </span>
                      </span>
                      <span className="njm-file-ok" aria-hidden="true">
                        <CheckCircle2 size={18} />
                      </span>
                      <button
                        type="button"
                        className="njm-file-remove"
                        onClick={() => handleRemoveFlatFile(file)}
                        disabled={state.saving}
                        aria-label={`Remove ${file.name}`}
                      >
                        <X size={15} aria-hidden="true" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Step 2, database path only. The connection sits here rather than
                on step 1 because it is what the tree below is a view OF -
                splitting them across two screens meant changing your mind about
                the connection was a Back, a re-pick and a Next. Rendered only
                while on screen, so the tree is not walking a catalog behind a
                hidden pane. */}
            {onTableStep ? (
              <div className="njm-stack">
                <div className="njm-field">
                  {/* No htmlFor: SearchableSelect owns its own input and takes
                      no id, so a htmlFor here would point at nothing. */}
                  <span className="njm-label is-required">Select Saved Connection</span>
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
                    Choose the database connection to use for this profiling job.
                  </span>
                </div>

                {state.connectionId && state.schemas && !state.loadingSchemas ? (
                  <SchemaTreePicker
                    rows={state.rows}
                    onChange={(rows) => setState((s) => ({ ...s, rows }))}
                    connectionId={state.connectionId}
                    schemas={state.schemas}
                    columnLabel="CDE"
                  />
                ) : !state.connectionId ? (
                  <p className="njm-waiting">
                    Choose a saved connection to browse its schemas and tables.
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
              /* type="button": this must not submit the form. Advancing is not
                 creating, and an Enter keypress on step 1 should do the same
                 thing as this button rather than skipping the table step. */
              <button
                key="btn-next"
                type="button"
                className="btn btn-primary"
                onClick={goNext}
                disabled={state.saving}
              >
                Next
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button key="btn-create" type="submit" className="btn btn-primary" disabled={state.saving}>
                {state.saving ? <Loader2 size={15} className="njm-spin" aria-hidden="true" /> : null}
                {createLabel}
              </button>
            )}
          </div>
        </form>
      </div>
    </ModalPortal>
  );
}
