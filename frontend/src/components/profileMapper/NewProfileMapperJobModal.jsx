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

export const NAME_MAX_LENGTH = 32;

const NAME_PLACEHOLDER = "e.g. Customer Master Profile - Sep 2026";
const DESCRIPTION_PLACEHOLDER = "Briefly describe what this profiling job covers…";
const MAX_CSV_BYTES = 200 * 1024 * 1024;
const MAX_CSV_MB = MAX_CSV_BYTES / (1024 * 1024);

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

const tableNameFor = (file) => file.name.replace(/\.csv$/i, "");

function findDuplicateName(names) {
  const seen = new Set();
  for (const name of names) {
    const key = name.toLowerCase();
    if (seen.has(key)) return name;
    seen.add(key);
  }
  return "";
}

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const EMPTY_STATE = {
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
  uploading: null,
};

export default function NewProfileMapperJobModal({ open, onClose, onCreated }) {
  const { showToast } = useToast();
  const [state, setState] = useState(EMPTY_STATE);
  const { options: connectionOptions, loading: loadingConnections } = useSavedConnections(open);
  const flatFileInputRef = useRef(null);

  const isDatabase = state.sourceType === SOURCE_TYPES.DATABASE;

  const hasTableStep = isDatabase;
  const onTableStep = state.step === 2;

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

  function databaseSelectionProblem() {
    if (!state.rows.some((row) => row.locked && row.schema && row.table && row.column)) {
      return {
        title: "No table selected",
        message: "Tick at least one table and give it a CDE column before creating this job.",
      };
    }
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
    e.preventDefault();
    const name = state.name.trim();
    const stepOneError = validateStepOne();
    if (stepOneError) {
      setState((s) => ({ ...s, error: stepOneError }));
      return;
    }
    if (isDatabase && !state.connectionId) {
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
      await attachFlatFiles(jobId, name);
    }

    handleClose();
    onCreated?.();
  }

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

            {onTableStep ? (
              <div className="njm-stack">
                <div className="njm-field">
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
