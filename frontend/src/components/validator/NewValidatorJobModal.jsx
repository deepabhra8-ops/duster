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

export const NAME_MAX_LENGTH = 32;

const NAME_PLACEHOLDER = "e.g. Orders DQ Validation - Sep 2026";
const DESCRIPTION_PLACEHOLDER = "Briefly describe what this validation run covers…";

const MAX_UPLOAD_MB = 50;

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const SOURCE_TYPE_CHOICES = [
  { value: SOURCE_TYPES.FLAT_FILE, label: "Flat File" },
  { value: SOURCE_TYPES.DATABASE, label: "Data Source" },
];

const EMPTY_STATE = {
  name: "",
  description: "",
  sourceType: SOURCE_TYPES.FLAT_FILE,
  step: 1,
  sourceMode: "job",
  profileMapJobId: "",
  uploadedMapFilename: "",
  lovFile: "",
  pickedFileName: "",
  pickedFileSize: 0,
  uploadedTables: [],
  connectionId: "",
  schemas: null,
  rows: [{ ...EMPTY_ROW }],
  loadingSchemas: false,
  saving: false,
  error: "",
  uploadError: "",
  inspecting: false
};

export default function NewValidatorJobModal({
  open,
  onClose,
  onCreated,
  initialSourceJobId = "",
}) {
  const [state, setState] = useState(EMPTY_STATE);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!open || !initialSourceJobId) return;
    setState((s) => ({ ...s, sourceMode: "job", profileMapJobId: initialSourceJobId }));
  }, [open, initialSourceJobId]);
  const { options: profileMapOptions, loading: loadingProfileMaps } = useCompletedProfileMapJobs(open);
  const { options: connectionOptions, loading: loadingConnections } = useSavedConnections(open);

  const isFlatFile = state.sourceType === SOURCE_TYPES.FLAT_FILE;

  const isUpload = state.sourceMode === "upload" && !isFlatFile;

  const hasTableStep = isUpload;
  const onTableStep = state.step === 2;

  function validateStepOne() {
    if (!state.name.trim()) return "Name is required";

    if (!isUpload) {
      return state.profileMapJobId ? "" : "Select a completed profile map";
    }

    if (!state.uploadedMapFilename) {
      return state.uploadError
        ? "This workbook was not accepted - see the error under Mapping Workbook. Fix it or choose another file."
        : "Choose a mapping workbook first";
    }

    return "";
  }

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

  function uncoveredTables(rows, expected) {
    const picked = new Set(
      rows.filter((r) => r.locked && r.schema && r.table).map((r) => r.table.toLowerCase())
    );
    return expected.filter((name) => !picked.has(String(name).toLowerCase()));
  }

  async function handleCreate(e) {
    e.preventDefault();

    const name = state.name.trim();

    const stepOneError = validateStepOne();
    if (stepOneError) {
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
                <div className="njm-source-grid" role="radiogroup" aria-label="Choose a source">
                  <div
                    role="radio"
                    aria-checked={!isUpload}
                    className={`njm-source-card${!isUpload ? " is-selected" : ""}`}
                    onClick={() => pickMode("job")}
                  >
                    <span className="njm-source-icon" aria-hidden="true">
                      <ClipboardCheck size={20} />
                    </span>
                    <span className="njm-source-text">
                      <span className="njm-source-title">Profile Mapper Job</span>
                      <span className="njm-source-desc">
                        Select from an existing profile mapper job
                      </span>
                    </span>
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

                    {state.uploadError && !state.inspecting && (
                      <div className="njm-alert" role="alert">
                        <AlertTriangle size={16} aria-hidden="true" />
                        <span>{state.uploadError}</span>
                      </div>
                    )}
                  </div>

                </>
              )}

              <LovUploadPanel
                compact
                className="njm-lov-section"
                value={state.lovFile || null}
                onChange={(filename) =>
                  setState((s) => ({ ...s, lovFile: filename || "" }))
                }
              />
            </div>

            {onTableStep ? (
              <div className="njm-stack">
                {tableCount > 0 ? (
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
