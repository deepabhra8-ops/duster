import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, FormField, Panel, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "bigquery";

/**
 * Dedicated "Connect BigQuery" screen. Field names mirror
 * backend/services/connectors/bigquery_connector.py's `required_fields`
 * (project_id, dataset_id) plus `service_account_json`, which its `validate()` also requires.
 * BigQuery access is granted through GCP IAM rather than SQL GRANTs, so this uses an info
 * Alert instead of the SQL least-privilege block the SQL-style connectors show.
 */
export default function BigQueryFormPage() {
  const navigate = useNavigate();
  const formRef = useRef(null);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  function readForm() {
    const data = new FormData(formRef.current);
    return {
      name: (data.get("name") || "").trim(),
      details: {
        project_id: data.get("project_id") || "",
        dataset_id: data.get("dataset_id") || "",
        service_account_json: data.get("service_account_json") || "",
      },
    };
  }

  async function handleTest() {
    const { details } = readForm();
    setTesting(true);
    setFeedback(null);
    const result = await testConnection(DB_TYPE, details);
    setTesting(false);

    if (result.ok && result.data?.ok) {
      setFeedback({ tone: "success", title: "Connection succeeded", message: result.data.message || "" });
    } else {
      setFeedback({ tone: "danger", title: "Connection failed", message: result.error || result.data?.error || "Please check your details and try again." });
    }
  }

  async function handleSave() {
    const { name, details } = readForm();

    if (!name) {
      setFeedback({ tone: "danger", title: "Name required", message: "Give this connection a name before saving." });
      return;
    }

    setSaving(true);
    const result = await createConnection(name, DB_TYPE, details);
    setSaving(false);

    if (result.ok && result.data?.data?.id) {
      navigate(`/connections/${result.data.data.id}/ingestion`);
    } else {
      setFeedback({ tone: "danger", title: "Couldn't save connection", message: result.error || "Please try again." });
    }
  }

  return (
    <>
      <SectionTabs items={CONNECTIONS_SECTION_TABS} />
      <div style={{ flex: "1 1 auto", overflowY: "auto", padding: "var(--space-6)", display: "flex", justifyContent: "center" }}>
        <div className="form-page" style={{ width: "100%", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect BigQuery" }]} />

          <div className="form-head">
            <div className="conn-icon">BQ</div>
            <div>
              <div className="form-title">Connect BigQuery</div>
              <div className="form-sub">Warehouse · service account</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="bq-name" name="name" label="Connection name" defaultValue="marketing-bigquery" />
                  <div className="sheet-field-row">
                    <FormField id="bq-project" name="project_id" label="Project ID" defaultValue="ds-marketing-prod" />
                    <FormField id="bq-dataset" name="dataset_id" label="Dataset ID" defaultValue="analytics" />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="bq-sa-json">
                      Service account JSON key
                    </label>
                    <textarea
                      id="bq-sa-json"
                      name="service_account_json"
                      className="field-input"
                      rows={6}
                      placeholder='{"type": "service_account", "project_id": "...", ...}'
                    />
                  </div>
                </div>
              </SheetSection>

              <Alert tone="info" title="Grant least-privilege IAM roles">
                Create a dedicated service account with only <code>roles/bigquery.dataViewer</code> and{" "}
                <code>roles/bigquery.jobUser</code> on this project, then paste its downloaded JSON key above. Duster
                never needs broader BigQuery Admin access.
              </Alert>

              {feedback ? <Alert tone={feedback.tone} title={feedback.title}>{feedback.message}</Alert> : null}
            </form>
          </Panel>

          <div className="form-footer">
            <Button register="ghost" to="/connections">Cancel</Button>
            <Button register="secondary" onClick={handleTest} disabled={testing}>
              {testing ? "Testing…" : "Test connection"}
            </Button>
            <Button register="primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save connection"}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
