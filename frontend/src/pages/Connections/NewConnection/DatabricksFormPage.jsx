import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, CodeBlock, FormField, Panel, SecurityNote, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "databricks";

const RBAC_SQL = `GRANT USE CATALOG ON CATALOG analytics TO \`duster_readonly\`;
GRANT USE SCHEMA ON SCHEMA analytics.public TO \`duster_readonly\`;
GRANT SELECT ON SCHEMA analytics.public TO \`duster_readonly\`;`;

/**
 * Dedicated "Connect Databricks" screen. Field names mirror
 * backend/services/connectors/databricks_connector.py's `required_fields`
 * (server_hostname, access_token, http_path) plus the optional catalog/schema.
 */
export default function DatabricksFormPage() {
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
        server_hostname: data.get("server_hostname") || "",
        http_path: data.get("http_path") || "",
        access_token: data.get("access_token") || "",
        catalog: data.get("catalog") || "",
        schema: data.get("schema") || "",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect Databricks" }]} />

          <div className="form-head">
            <div className="conn-icon">DBX</div>
            <div>
              <div className="form-title">Connect Databricks</div>
              <div className="form-sub">Lakehouse · token-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="dbx-name" name="name" label="Connection name" defaultValue="lakehouse-databricks" />
                  <FormField id="dbx-hostname" name="server_hostname" label="Server hostname" defaultValue="dbc-a1b2c3d4-e5f6.cloud.databricks.com" />
                  <FormField id="dbx-http-path" name="http_path" label="HTTP path" defaultValue="/sql/1.0/warehouses/abcd1234ef567890" />
                  <FormField id="dbx-token" name="access_token" label="Access token" type="password" />
                  <div className="sheet-field-row">
                    <FormField id="dbx-catalog" name="catalog" label="Catalog (optional)" defaultValue="analytics" />
                    <FormField id="dbx-schema" name="schema" label="Schema (optional)" defaultValue="public" />
                  </div>
                </div>
              </SheetSection>

              <SheetSection title="Least-privilege setup">
                <p className="form-section-hint">Run this in Databricks Unity Catalog to grant Duster read-only access.</p>
                <CodeBlock sql={RBAC_SQL} />
              </SheetSection>

              <SecurityNote>
                Generate a personal access token scoped to a read-only service principal, and add Duster&rsquo;s static IPs
                (<code>34.66.12.0/24</code>) to this workspace&rsquo;s IP access list before testing.
              </SecurityNote>

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
