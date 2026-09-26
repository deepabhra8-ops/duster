import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, CodeBlock, FormField, Panel, SecurityNote, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "snowflake";

const RBAC_SQL = `CREATE ROLE duster_readonly;
GRANT USAGE ON WAREHOUSE analytics_wh TO ROLE duster_readonly;
GRANT USAGE ON DATABASE analytics TO ROLE duster_readonly;
GRANT USAGE ON SCHEMA analytics.public TO ROLE duster_readonly;
GRANT SELECT ON ALL TABLES
  IN SCHEMA analytics.public TO ROLE duster_readonly;
GRANT ROLE duster_readonly TO USER duster_svc;`;

/**
 * Dedicated "Connect Snowflake" screen. Field names mirror
 * backend/services/connectors/snowflake_connector.py's `required_fields`
 * (account, username, password, warehouse, database, schema) plus the optional role.
 */
export default function SnowflakeFormPage() {
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
        account: data.get("account") || "",
        username: data.get("username") || "",
        password: data.get("password") || "",
        warehouse: data.get("warehouse") || "",
        database: data.get("database") || "",
        schema: data.get("schema") || "",
        role: data.get("role") || "",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect Snowflake" }]} />

          <div className="form-head">
            <div className="conn-icon">SNOW</div>
            <div>
              <div className="form-title">Connect Snowflake</div>
              <div className="form-sub">Warehouse · credential-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="sf-name" name="name" label="Connection name" defaultValue="analytics-snowflake" />
                  <div className="sheet-field-row">
                    <FormField id="sf-account" name="account" label="Account identifier" defaultValue="xj4821" />
                    <FormField id="sf-warehouse" name="warehouse" label="Warehouse" defaultValue="analytics_wh" />
                  </div>
                  <div className="sheet-field-row">
                    <FormField id="sf-database" name="database" label="Database" defaultValue="analytics" />
                    <FormField id="sf-schema" name="schema" label="Schema" defaultValue="public" />
                  </div>
                  <div className="sheet-field-row">
                    <FormField id="sf-username" name="username" label="Username" defaultValue="duster_svc" />
                    <FormField id="sf-password" name="password" label="Password" type="password" />
                  </div>
                  <FormField id="sf-role" name="role" label="Role (optional)" defaultValue="duster_readonly" />
                </div>
              </SheetSection>

              <SheetSection title="Least-privilege setup">
                <p className="form-section-hint">Run this in Snowflake to grant Duster read-only access scoped to this warehouse and schema.</p>
                <CodeBlock sql={RBAC_SQL} />
              </SheetSection>

              <SecurityNote>
                Duster connects from a fixed set of static IPs. If this account uses network policies, add
                <code> 34.66.12.0/24</code> to the allowed list before testing.
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
