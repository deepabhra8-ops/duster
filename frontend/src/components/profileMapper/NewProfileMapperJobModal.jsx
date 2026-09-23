import { useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Database,
  FileSearch,
  Loader2,
  X,
} from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import SearchableSelect from "../SearchableSelect.jsx";
import SchemaTreePicker, { EMPTY_ROW } from "./SchemaTreePicker.jsx";
import {
  createDraftJob,
  listConnectionSchemas,
  updateJobTables,
} from "../../api/api.js";
import { useSavedConnections } from "../../hooks/useSavedConnections.js";
import { useToast } from "../../hooks/useToast.js";
import { preventEnterSubmit } from "../../utils/helpers.js";
import { rowsToTables } from "../../utils/profileMapperRows.js";
import ModalPortal from "../ModalPortal.jsx";
import "../../styles/new-job-modal.css";

export const NAME_MAX_LENGTH = 32;

const NAME_PLACEHOLDER = "e.g. Customer Master Profile - Sep 2026";
const DESCRIPTION_PLACEHOLDER = "Briefly describe what this profiling job covers…";

function findDuplicateName(names) {
  const seen = new Set();
  for (const name of names) {
    const key = name.toLowerCase();
    if (seen.has(key)) return name;
    seen.add(key);
  }
  return "";
}

const EMPTY_STATE = {
  step: 1,
  name: "",
  description: "",
  connectionId: "",
  schemas: null,
  rows: [{ ...EMPTY_ROW }],
  loadingSchemas: false,
  error: "",
  saving: false,
};

export default function NewProfileMapperJobModal({ open, onClose, onCreated }) {
  const { showToast } = useToast();
  const [state, setState] = useState(EMPTY_STATE);
  const { options: connectionOptions, loading: loadingConnections } = useSavedConnections(open);

  const onTableStep = state.step === 2;

  function validateStepOne() {
    if (!state.name.trim()) return "Name is required";
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
    if (!state.connectionId) {
      setState((s) => ({ ...s, step: 2, error: "Select a saved connection" }));
      return;
    }
    const selectionProblem = databaseSelectionProblem();
    if (selectionProblem) {
      showToast({ type: "error", ...selectionProblem });
      return;
    }

    setState((s) => ({ ...s, saving: true, error: "" }));
    const { ok, data, error } = await createDraftJob(
      name,
      state.description.trim(),
      state.connectionId,
      "1"
    );
    if (!ok) {
      setState((s) => ({ ...s, saving: false, error: error || "Failed to create job" }));
      return;
    }

    const jobId = data.job_id;
    const tables = rowsToTables(state.rows);
    if (tables.length) await updateJobTables(jobId, tables);

    handleClose();
    onCreated?.();
  }

  useScrollLock(open);

  if (!open) return null;

  const createLabel = state.saving ? "Creating…" : "Create";

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
                  New Job{onTableStep ? " - Select Tables" : " - Details"}
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

              <p className="njm-hint">
                You will choose the connection and its tables on the next screen.
              </p>
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

            {!onTableStep ? (
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
