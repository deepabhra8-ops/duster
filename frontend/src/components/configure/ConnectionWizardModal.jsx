import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Database,
  Loader2,
  Play,
  PlugZap,
  X,
} from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import ModalPortal from "../ModalPortal.jsx";
import DatabaseFields from "./DatabaseFields.jsx";
import DatabaseFieldsSkeleton from "./DatabaseFieldsSkeleton.jsx";
import { DB_FIELD_CONFIGS, DB_REQUIRED_FIELDS } from "../../constants/dbFields.js";
import { DATABASE_TYPE_OPTIONS } from "../../constants/sourceTypes.js";
import {
  createConnection,
  revealConnection,
  testConnection,
  updateConnection,
} from "../../api/api.js";
import "../../styles/new-job-modal.css";

const NAMING_GUIDANCE_SHORT = "Give a unique and meaningful name for this connection.";

const NAME_MAX_LENGTH = 64;
const DESCRIPTION_MAX_LENGTH = 200;

const EMPTY_STATE = { step: 1, name: "", description: "", dbType: "", details: {}, error: "" };

export default function ConnectionWizardModal({ open, onClose, onSaved, editingConnection = null }) {
  const [state, setState] = useState(EMPTY_STATE);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const isEditing = Boolean(editingConnection);

  useEffect(() => {
    if (!open || !editingConnection) return;

    let cancelled = false;
    setState({
      step: 1,
      name: editingConnection.name || "",
      description: editingConnection.description || "",
      dbType: editingConnection.db_type || "",
      details: {},
      error: "",
    });
    setLoadingDetails(true);

    revealConnection(editingConnection.id).then(({ ok, data, error }) => {
      if (cancelled) return;
      setLoadingDetails(false);
      if (!ok) {
        setState((s) => ({ ...s, error: error || "Failed to load connection details" }));
        return;
      }
      setState((s) => ({ ...s, details: data?.data?.connection_details || {} }));
    });

    return () => {
      cancelled = true;
    };
  }, [open, editingConnection]);

  function reset() {
    setState(EMPTY_STATE);
    setTesting(false);
    setTestResult(null);
    setSaving(false);
    setLoadingDetails(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function goNext() {
    if (!state.name.trim()) {
      setState((s) => ({ ...s, error: "Name is required" }));
      return;
    }
    setState((s) => ({ ...s, step: 2, error: "" }));
  }

  function goBack() {
    setState((s) => ({ ...s, step: 1, error: "" }));
  }

  function setDetail(id, value) {
    setState((s) => ({ ...s, details: { ...s.details, [id]: value } }));
    setTestResult(null);
  }

  async function runConnectionTest() {
    const required = DB_REQUIRED_FIELDS[state.dbType] || [];
    const missing = required.filter((f) => !String(state.details[f] ?? "").trim());
    if (missing.length) {
      const labels = (DB_FIELD_CONFIGS[state.dbType] || [])
        .filter((f) => missing.includes(f.id))
        .map((f) => f.label);
      const result = { ok: false, msg: `Missing: ${labels.join(", ")}` };
      setTestResult(result);
      return result;
    }
    const { ok, data, error } = await testConnection(state.dbType, state.details);
    const result = { ok, msg: ok ? data?.message || "Connected!" : error || "Failed" };
    setTestResult(result);
    return result;
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    await runConnectionTest();
    setTesting(false);
  }

  async function handleSave() {
    if (!state.dbType) {
      setState((s) => ({ ...s, step: 2, error: "Select a database type" }));
      return;
    }

    setSaving(true);
    setState((s) => ({ ...s, error: "" }));
    setTestResult(null);

    const testOutcome = await runConnectionTest();
    if (!testOutcome.ok) {
      setSaving(false);
      return;
    }

    if (isEditing) {
      const { ok, data, error } = await updateConnection(
        editingConnection.id,
        state.name.trim(),
        state.dbType,
        state.details,
        state.description.trim()
      );
      setSaving(false);
      if (!ok) {
        setState((s) => ({ ...s, error: error || "Failed to save connection" }));
        return;
      }
      onSaved(data?.data);
      reset();
      return;
    }

    const { ok, data, error } = await createConnection(
      state.name.trim(),
      state.dbType,
      state.details,
      state.description.trim()
    );
    setSaving(false);
    if (!ok) {
      setState((s) => ({ ...s, error: error || "Failed to save connection" }));
      return;
    }

    onSaved(data?.data);
    reset();
  }

  useScrollLock(open);

  if (!open) return null;

  const stepTitle = isEditing
    ? state.step === 1
      ? "Edit Connection"
      : "Edit Connection - Details"
    : state.step === 1
      ? "New Connection"
      : "New Connection - Details";

  return (
    <ModalPortal>
      <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && handleClose()}>
        <div className="njm njm-wide modal-box wizard-box wizard-box-sm">
          <div className="njm-header">
            <div className="njm-header-main">
              <span className="njm-header-icon" aria-hidden="true">
                <Database size={20} />
              </span>
              <span>
                <span className="njm-title">{stepTitle}</span>
                <span className="njm-subtitle">
                  {state.step === 1
                    ? "Name this connection so your team recognises it later."
                    : "Configure the details to connect to your database."}
                </span>
              </span>
            </div>
            <button type="button" className="njm-close" onClick={handleClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          <div className="njm-body">
            {state.step === 1 ? (
              <div className="njm-stack">
                <div className="njm-field">
                  <label className="njm-label is-required" htmlFor="conn-name">Connection Name</label>
                  <input
                    id="conn-name"
                    type="text"
                    maxLength={NAME_MAX_LENGTH}
                    placeholder="e.g. Prod Postgres - Orders DB"
                    value={state.name}
                    onChange={(e) => setState((s) => ({ ...s, name: e.target.value, error: "" }))}
                  />
                  <span className="njm-field-foot">
                    <span className="njm-hint">{NAMING_GUIDANCE_SHORT}</span>
                    <span className="njm-count">
                      {state.name.length}/{NAME_MAX_LENGTH}
                    </span>
                  </span>
                </div>

                <div className="njm-field">
                  <label className="njm-label" htmlFor="conn-description">
                    Description<span className="njm-optional"> (Optional)</span>
                  </label>
                  <textarea
                    id="conn-description"
                    maxLength={DESCRIPTION_MAX_LENGTH}
                    placeholder="What is this connection for?"
                    value={state.description}
                    onChange={(e) => setState((s) => ({ ...s, description: e.target.value }))}
                  />
                  <span className="njm-field-foot">
                    <span className="njm-hint">Helps others understand the purpose of this connection.</span>
                    <span className="njm-count">
                      {state.description.length}/{DESCRIPTION_MAX_LENGTH}
                    </span>
                  </span>
                </div>
              </div>
            ) : (
              <div className="njm-stack">
                <div className="njm-field">
                  <label className="njm-label is-required" htmlFor="conn-db-type">Select Database</label>
                  <span className="njm-input-wrap">
                    <span className="njm-input-icon" aria-hidden="true">
                      <Database size={15} />
                    </span>
                    <select
                      id="conn-db-type"
                      className="njm-select"
                      value={state.dbType}
                      onChange={(e) =>
                        setState((s) => ({ ...s, dbType: e.target.value, details: {}, error: "" }))
                      }
                    >
                      {DATABASE_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </span>
                  <span className="njm-hint">
                    The fields below change to match the database you pick.
                  </span>
                </div>

                {state.dbType ? (
                  loadingDetails ? (
                    <DatabaseFieldsSkeleton dbType={state.dbType} />
                  ) : (
                    <>
                      <DatabaseFields
                        dbType={state.dbType}
                        details={state.details}
                        onChange={setDetail}
                        enhanced
                      />

                      <div className={`njm-test${testResult ? (testResult.ok ? " is-ok" : " is-err") : ""}`}>
                        <span className="njm-test-icon" aria-hidden="true">
                          {testResult ? (
                            testResult.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />
                          ) : (
                            <PlugZap size={16} />
                          )}
                        </span>
                        <span className="njm-test-text">
                          {testResult
                            ? testResult.msg
                            : "Test the connection below to verify the details are correct."}
                        </span>
                      </div>
                    </>
                  )
                ) : (
                  <p className="njm-waiting">
                    Pick a database above to configure its connection details.
                  </p>
                )}
              </div>
            )}

            {state.error ? (
              <div className="njm-alert" role="alert">
                <AlertTriangle size={16} aria-hidden="true" />
                <span>{state.error}</span>
              </div>
            ) : null}
          </div>

          <div className="njm-footer">
            {state.step === 1 ? (
              <button type="button" className="btn btn-ghost" onClick={handleClose}>
                Cancel
              </button>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={goBack}>
                <ArrowLeft size={15} aria-hidden="true" />
                Back
              </button>
            )}

            {state.step === 2 && state.dbType ? (
              <button
                type="button"
                className="btn btn-ghost njm-test-btn"
                disabled={testing || saving || loadingDetails}
                onClick={handleTest}
              >
                {testing ? (
                  <Loader2 size={14} className="njm-spin" aria-hidden="true" />
                ) : (
                  <Play size={14} aria-hidden="true" />
                )}
                {testing ? "Testing…" : "Test Connection"}
              </button>
            ) : null}

            {state.step === 1 ? (
              <button type="button" className="btn btn-primary" onClick={goNext}>
                Next
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button type="button" className="btn btn-primary" disabled={saving || loadingDetails} onClick={handleSave}>
                {saving ? <Loader2 size={15} className="njm-spin" aria-hidden="true" /> : null}
                {saving ? (testResult ? "Saving…" : "Testing…") : isEditing ? "Save" : "Save & Connect"}
              </button>
            )}
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
