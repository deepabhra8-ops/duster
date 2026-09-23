/**
 * ConnectionWizardModal.jsx - 2-step "Create/Edit connection" wizard for
 * the Connections manager (Connections.jsx).
 *
 * Step 1: Name and Description - who this connection is, nothing else.
 * Step 2: the database type AND the dynamic connection fields it selects
 *         (DatabaseFields, `enhanced`, the same component the old Configure
 *         page's Source Connection card uses) + Test Connection, then Save.
 *
 * The type used to sit on step 1. It belongs here instead: every field on this
 * screen exists because of it, so choosing it on the previous screen meant
 * changing your mind cost a Back, a re-pick and a Next - with the fields you
 * were looking at replaced on the way past.
 *
 * Presentation comes from styles/new-job-modal.css (the `njm` class), shared
 * with the Profile Mapper and Validator New Job wizards so all three dialogs
 * read as one thing. `njm-wide` is this modal's own width: the credential
 * fields are a two-column grid, which the 660px the others use leaves cramped.
 *
 * Edit mode: pass `editingConnection` (the row from the table - id, name,
 * db_type, description; never connection_details, which the list endpoint
 * never returns) to prefill Name/Description/Database Type on open, then
 * fetch its decrypted details via GET /api/connections/{id}/reveal (same
 * endpoint the New Job wizard already uses right after picking a saved
 * connection - see that route's own docstring on why this isn't a new
 * exposure) to prefill step 2's fields. `.wizard-loading-overlay` (shared
 * with NewProfileMapperJobModal.jsx) covers the modal while that reveal is
 * in flight. Save then PATCHes (updateConnection) instead of POSTing
 * (createConnection); either way, on success it calls `onSaved` with the
 * server's updated/created non-secret row. Passing `editingConnection={null}`
 * (or omitting it) is create mode.
 *
 * Saving does no catalog work. It used to: creating a connection ran a schema
 * query server-side and blocked the whole viewport behind a
 * `.fullscreen-loading-overlay` reading "Saving connection and reading
 * schemas...", so the user waited on a catalog read to finish a step that only
 * needed an insert. The stored schema list also went stale - a schema added to
 * the source afterwards never appeared until someone pressed refresh.
 *
 * Schemas are now read live when a connection is actually picked for a
 * profiling or validation job, exactly like tables and columns already were
 * (see migration 007 and SavedConnectionService.list_schemas). Saving is a
 * plain insert, so the button's own "Saving..." state is all the feedback it
 * needs and the blocking overlay is gone.
 */
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

/** Shown as the Name field's hint. Short on purpose: it sits under the input
 *  permanently rather than behind a tooltip, so it has to earn its line. */
const NAMING_GUIDANCE_SHORT = "Give a unique and meaningful name for this connection.";

/** Caps that match the other New Job wizards, so the counters mean the same
 *  thing everywhere. Both are UI-side only - neither column is length-limited
 *  server-side, so these truncate nothing that was previously storable. */
const NAME_MAX_LENGTH = 64;
const DESCRIPTION_MAX_LENGTH = 200;

const EMPTY_STATE = { step: 1, name: "", description: "", dbType: "", details: {}, error: "" };

export default function ConnectionWizardModal({ open, onClose, onSaved, editingConnection = null }) {
  const [state, setState] = useState(EMPTY_STATE);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null); // { ok, msg }
  const [saving, setSaving] = useState(false);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const isEditing = Boolean(editingConnection);

  /* Prefill from the known list row, then fetch its decrypted details. */
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

  /* Step 1 is identity only now - the database type moved to step 2, beside
     the fields it decides. */
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

  /**
   * Runs the same check handleTest does (missing-fields, then the real
   * test-connection call) and reports through the same `testResult` box, but
   * returns the outcome instead of just displaying it - so handleSave can gate
   * on it without duplicating the logic.
   */
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
    /* Guards the type here because step 1 no longer can. Without it a
       connection could be saved with db_type "" - accepted by the form, then
       unusable by every job that later picks it. */
    if (!state.dbType) {
      setState((s) => ({ ...s, step: 2, error: "Select a database type" }));
      return;
    }

    setSaving(true);
    setState((s) => ({ ...s, error: "" }));
    setTestResult(null);

    /* Wrong credentials used to save fine - the "Test Connection" button was
       purely optional, so a user who never pressed it (or who fixed a typo
       after the last successful test) could save something no job could ever
       actually connect to. Every save now re-runs the same test the button
       does; on failure nothing is written to either endpoint and the modal
       stays open exactly as it does after a manual failed test, so the user
       can fix the details and try again (or Cancel to discard) rather than
       silently getting a broken connection either way - new or edited. */
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

    // Create mode: a plain insert. No catalog read - see the header comment.
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

    // Saving does no catalog work at all now - schemas are read live when the
    // connection is picked for a job, like tables and columns. That removes the
    // "fetching schemas" wait from a step that never needed it, and with it the
    // warning toast for a schema read that failed without invalidating the save.
    onSaved(data?.data);
    reset();
  }

  // Freeze the page behind the overlay - see the hook for why a plain
  // body overflow:hidden is not enough (nesting, scrollbar layout shift).
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
                    {/* The naming guidance used to hide behind an ℹ️ tooltip next
                        to the label. It is one short sentence and it is advice
                        you want BEFORE typing, so it reads as the field's hint
                        instead of something to go hunting for. */}
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
                {/* The database type opens step 2 rather than closing step 1:
                    every field below it exists BECAUSE of it, so the two belong
                    on one screen. Choosing a type on the previous screen meant
                    changing your mind cost a Back, a re-pick and a Next, with
                    the fields you were looking at replaced on the way. */}
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

                      {/* The outcome only - the button that produces it lives in
                          the footer with the other actions, since testing is one
                          of the three things you can do from this screen rather
                          than a field in the form. */}
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

            {/* Between Back and Save: it is the step you take before committing,
                so it reads left-to-right in the order you would do them. */}
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
                {/* Save always tests first now - testResult is still null for the
                    part of `saving` spent on that check, and set (ok either way)
                    by the time the actual create/update call is in flight. */}
                {saving ? (testResult ? "Saving…" : "Testing…") : isEditing ? "Save" : "Save & Connect"}
              </button>
            )}
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
