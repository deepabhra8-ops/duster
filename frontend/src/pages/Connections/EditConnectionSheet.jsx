import { useEffect, useRef, useState } from "react";
import { Alert, Button, FormField, Sheet, SheetSection } from "../../design-system/components/index.js";
import { revealConnection, testConnection, updateConnection } from "../../api/api.js";
import { CONNECTOR_CATALOG } from "./connectorCatalog.js";
import { fieldsForDbType } from "./connectionFields.js";

function renderField(field, defaultValue) {
  if (field.type === "textarea") {
    const id = `edit-${field.name}`;
    return (
      <div key={field.name}>
        <label className="field-label" htmlFor={id}>
          {field.label}
        </label>
        <textarea id={id} name={field.name} className="field-input" rows={6} defaultValue={defaultValue} />
      </div>
    );
  }

  return (
    <FormField
      key={field.name}
      id={`edit-${field.name}`}
      name={field.name}
      label={field.label}
      type={field.type}
      options={field.options}
      defaultValue={defaultValue}
    />
  );
}

/**
 * The right-side "Edit connection" panel — same Sheet shell as AddConnectionSheet, but showing
 * one connector's fields (from connectionFields.js) instead of the source catalog. Reveals the
 * connection's decrypted details on open so the form is prefilled with real values, same as the
 * "Add connection" screens ship with realistic sample defaults.
 */
export function EditConnectionSheet({ isOpen, connection, onClose, onSaved }) {
  const formRef = useRef(null);
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    if (!isOpen || !connection) return undefined;

    let cancelled = false;
    setDetails(null);
    setFeedback(null);
    setLoading(true);

    revealConnection(connection.id).then((result) => {
      if (cancelled) return;
      setLoading(false);

      if (result.ok) {
        setDetails(result.data?.data?.connection_details || {});
      } else {
        setDetails({});
        setFeedback({
          tone: "danger",
          title: "Couldn't load connection details",
          message: result.error || "Please try again.",
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isOpen, connection]);

  if (!connection) return null;

  const dbType = connection.dbType;
  const fieldGroups = fieldsForDbType(dbType);
  const catalogEntry = CONNECTOR_CATALOG.find((c) => c.id === dbType);

  function readForm() {
    const data = new FormData(formRef.current);
    const out = {};
    fieldGroups.flat().forEach((field) => {
      out[field.name] = data.get(field.name) || "";
    });
    return { name: (data.get("name") || "").trim(), details: out };
  }

  async function handleTest() {
    const { details: submitted } = readForm();
    setTesting(true);
    setFeedback(null);
    const result = await testConnection(dbType, submitted);
    setTesting(false);

    if (result.ok && result.data?.ok) {
      setFeedback({ tone: "success", title: "Connection succeeded", message: result.data.message || "" });
    } else {
      setFeedback({
        tone: "danger",
        title: "Connection failed",
        message: result.error || result.data?.error || "Please check your details and try again.",
      });
    }
  }

  async function handleSave() {
    const { name, details: submitted } = readForm();

    if (!name) {
      setFeedback({ tone: "danger", title: "Name required", message: "Give this connection a name before saving." });
      return;
    }

    setSaving(true);
    const result = await updateConnection(connection.id, name, dbType, submitted, connection.description || "");
    setSaving(false);

    if (result.ok) {
      onSaved?.();
      onClose();
    } else {
      setFeedback({ tone: "danger", title: "Couldn't save connection", message: result.error || "Please try again." });
    }
  }

  return (
    <Sheet
      isOpen={isOpen}
      onClose={onClose}
      eyebrow={catalogEntry?.category}
      title={`Edit ${connection.name}`}
      titleIcon={<span className="conn-icon">{catalogEntry?.icon || String(dbType || "").toUpperCase()}</span>}
      footer={
        <>
          <Button register="ghost" onClick={onClose}>
            Cancel
          </Button>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button register="secondary" onClick={handleTest} disabled={loading || testing}>
              {testing ? "Testing…" : "Test connection"}
            </Button>
            <Button register="primary" onClick={handleSave} disabled={loading || saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </>
      }
    >
      {loading ? (
        <p className="connections-muted">Loading connection details&hellip;</p>
      ) : (
        <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <SheetSection title="Connection details">
            <div className="form-field-stack">
              <FormField id="edit-name" name="name" label="Connection name" defaultValue={connection.name} />
              {fieldGroups.map((row, i) =>
                row.length === 2 ? (
                  <div className="sheet-field-row" key={i}>
                    {row.map((field) => renderField(field, details?.[field.name] ?? ""))}
                  </div>
                ) : (
                  <div key={i}>{renderField(row[0], details?.[row[0].name] ?? "")}</div>
                )
              )}
            </div>
          </SheetSection>

          {feedback ? (
            <Alert tone={feedback.tone} title={feedback.title}>
              {feedback.message}
            </Alert>
          ) : null}
        </form>
      )}
    </Sheet>
  );
}

export default EditConnectionSheet;
