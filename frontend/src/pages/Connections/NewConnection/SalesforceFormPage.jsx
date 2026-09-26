import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, FormField, Panel, SheetSection } from "../../../design-system/components/index.js";
import { createConnection, testConnection } from "../../../api/api.js";

const DB_TYPE = "salesforce";

/**
 * Dedicated "Connect Salesforce" screen. Field names mirror
 * backend/services/connectors/salesforce_connector.py's `required_fields`
 * (username, password, security_token, domain). Salesforce access is scoped through
 * Profiles/Permission Sets rather than SQL GRANTs, so this uses an info Alert instead of
 * the SQL least-privilege block the SQL-style connectors show.
 */
export default function SalesforceFormPage() {
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
        username: data.get("username") || "",
        password: data.get("password") || "",
        security_token: data.get("security_token") || "",
        domain: data.get("domain") || "login",
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
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect Salesforce" }]} />

          <div className="form-head">
            <div className="conn-icon">SF</div>
            <div>
              <div className="form-title">Connect Salesforce</div>
              <div className="form-sub">SaaS &amp; data catalogs · credential-based</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Connection details">
                <div className="form-field-stack">
                  <FormField id="sfc-name" name="name" label="Connection name" defaultValue="salesforce-crm" />
                  <FormField id="sfc-username" name="username" label="Username" defaultValue="duster-integration@company.com" />
                  <div className="sheet-field-row">
                    <FormField id="sfc-password" name="password" label="Password" type="password" />
                    <FormField id="sfc-token" name="security_token" label="Security token" type="password" />
                  </div>
                  <FormField id="sfc-domain" name="domain" label="Login domain" options={["login", "test"]} defaultValue="login" />
                </div>
              </SheetSection>

              <Alert tone="info" title="Use a dedicated integration user">
                Create a Salesforce user with a minimal Permission Set (read-only object and field access) instead of
                reusing an admin login, and reset its security token if it&rsquo;s ever rotated.
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
