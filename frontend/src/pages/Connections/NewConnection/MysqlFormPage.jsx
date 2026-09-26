import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, CodeBlock, FormField, Panel, SecurityNote, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "mysql";

const RBAC_SQL = `CREATE USER 'duster_readonly'@'%' IDENTIFIED BY '...';
GRANT SELECT ON analytics.*
  TO 'duster_readonly'@'%';`;

/**
 * Dedicated "Connect MySQL" screen. Field names mirror
 * backend/services/connectors/mysql_connector.py's `required_fields`
 * (host, username, password) plus the optional database/port/ssl_enabled the connector reads.
 */
export default function MysqlFormPage() {
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
        ssl_enabled: data.get("ssl_enabled") === "Enabled (recommended)",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect MySQL" }]} />

          <div className="form-head">
            <div className="conn-icon">MY</div>
            <div>
              <div className="form-title">Connect MySQL</div>
              <div className="form-sub">Database · credential-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="my-name" name="name" label="Connection name" defaultValue="billing-mysql" />
                  <div className="sheet-field-row">
                    <FormField id="my-host" name="host" label="Host" defaultValue="billing-prod.rds.aws" />
                    <FormField id="my-port" name="port" label="Port" defaultValue="3306" />
                  </div>
                  <FormField id="my-database" name="database" label="Database" defaultValue="billing" />
                  <div className="sheet-field-row">
                    <FormField id="my-username" name="username" label="Username" defaultValue="duster_readonly" />
                    <FormField id="my-password" name="password" label="Password" type="password" />
                  </div>
                  <FormField id="my-ssl" name="ssl_enabled" label="SSL" options={["Enabled (recommended)", "Disabled"]} defaultValue="Enabled (recommended)" />
                </div>
              </SheetSection>

              <SheetSection title="Least-privilege setup">
                <p className="form-section-hint">Run this in MySQL to grant Duster read-only access scoped to this database.</p>
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
