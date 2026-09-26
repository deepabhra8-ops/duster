import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, CodeBlock, FormField, Panel, SecurityNote, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "redshift";

const RBAC_SQL = `CREATE USER duster_readonly PASSWORD '...';
GRANT SELECT ON ALL TABLES
  IN SCHEMA public TO duster_readonly;`;

/**
 * Dedicated "Connect Redshift" screen. Field names mirror
 * backend/services/connectors/redshift_connector.py's `required_fields`
 * (host, username, password, database) plus the optional port/ssl_enabled the connector reads.
 * Redshift's RBAC snippet uses CREATE USER (not CREATE ROLE like Postgres) — intentional,
 * matching Redshift's actual grant model. Wired to the real test/create endpoints.
 */
export default function RedshiftFormPage() {
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
        ssl_enabled: data.get("ssl") === "Enabled (recommended)",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect Redshift" }]} />

          <div className="form-head">
            <div className="conn-icon">RS</div>
            <div>
              <div className="form-title">Connect Redshift</div>
              <div className="form-sub">Warehouse · credential-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="rs-name" name="name" label="Connection name" defaultValue="warehouse-redshift" />
                  <div className="sheet-field-row">
                    <FormField id="rs-host" name="host" label="Host (cluster endpoint)" defaultValue="wh-prod.abc123xyz.us-east-1.redshift.amazonaws.com" />
                    <FormField id="rs-port" name="port" label="Port" defaultValue="5439" />
                  </div>
                  <FormField id="rs-database" name="database" label="Database" defaultValue="analytics" />
                  <div className="sheet-field-row">
                    <FormField id="rs-username" name="username" label="Username" defaultValue="duster_readonly" />
                    <FormField id="rs-password" name="password" label="Password" type="password" />
                  </div>
                  <FormField id="rs-ssl" name="ssl" label="SSL" options={["Enabled (recommended)", "Disabled"]} defaultValue="Enabled (recommended)" />
                </div>
              </SheetSection>

              <SheetSection title="Least-privilege setup">
                <p className="form-section-hint">Run this in Redshift to grant Duster read-only access scoped to this database.</p>
                <CodeBlock sql={RBAC_SQL} />
              </SheetSection>

              <SecurityNote>
                Duster connects from a fixed set of static IPs. Add <code>34.66.12.0/24</code> to this cluster&rsquo;s inbound security
                group before testing.
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
