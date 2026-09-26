import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, CodeBlock, FormField, Panel, SecurityNote, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "postgresql";

const RBAC_SQL = `CREATE ROLE duster_readonly WITH LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE analytics TO duster_readonly;
GRANT USAGE ON SCHEMA public TO duster_readonly;
GRANT SELECT ON ALL TABLES
  IN SCHEMA public TO duster_readonly;`;

/**
 * Dedicated "Connect PostgreSQL" screen — its own page, not a shared form fed different
 * props. Field names mirror backend/services/connectors/postgresql_connector.py's
 * `required_fields` (host, username, password) plus the optional database/port/ssl_mode
 * the connector reads. Wired to the real test-connection/create-connection endpoints.
 */
export default function PostgresFormPage() {
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
        host: data.get("host") || "",
        port: data.get("port") || "",
        database: data.get("database") || "",
        username: data.get("username") || "",
        password: data.get("password") || "",
        ssl_mode: data.get("ssl_mode") || "",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect PostgreSQL" }]} />

          <div className="form-head">
            <div className="conn-icon">PG</div>
            <div>
              <div className="form-title">Connect PostgreSQL</div>
              <div className="form-sub">Database · credential-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="pg-name" name="name" label="Connection name" defaultValue="prod-postgres" />
                  <div className="sheet-field-row">
                    <FormField id="pg-host" name="host" label="Host" defaultValue="analytics-prod.rds.amazonaws.com" />
                    <FormField id="pg-port" name="port" label="Port" defaultValue="5432" />
                  </div>
                  <FormField id="pg-database" name="database" label="Database" defaultValue="analytics" />
                  <div className="sheet-field-row">
                    <FormField id="pg-username" name="username" label="Username" defaultValue="duster_readonly" />
                    <FormField id="pg-password" name="password" label="Password" type="password" />
                  </div>
                  <FormField id="pg-sslmode" name="ssl_mode" label="SSL mode" options={["require", "verify-full", "disable"]} defaultValue="require" />
                </div>
              </SheetSection>

              <SheetSection title="Least-privilege setup">
                <p className="form-section-hint">Run this in PostgreSQL to grant Duster read-only access scoped to this database.</p>
                <CodeBlock sql={RBAC_SQL} />
              </SheetSection>

              <SecurityNote>
                Duster connects from a fixed set of static IPs. Add <code>34.66.12.0/24</code> to this database&rsquo;s inbound rules
                before testing.
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
