import { ExternalLink } from "lucide-react";
import SectionTabs from "../../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "../sectionTabs.js";
import { Alert, Breadcrumb, Button, FormField, Panel, SheetSection } from "../../../design-system/components/index.js";

/**
 * Dedicated "Connect dbt Cloud" screen — the token/OAuth style of connector, distinct from
 * the credential-based database forms. No backend connector exists for dbt Cloud yet (see
 * backend/services/connectors/ — there's no dbt_cloud_connector.py), so these fields are
 * illustrative rather than pulled from a real schema. Static/sample: no real submit handler.
 */
export default function DbtCloudFormPage() {
  return (
    <>
      <SectionTabs items={CONNECTIONS_SECTION_TABS} />
      <div style={{ flex: "1 1 auto", overflowY: "auto", padding: "var(--space-6)", display: "flex", justifyContent: "center" }}>
        <div className="form-page" style={{ width: "100%", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Breadcrumb segments={[{ label: "Connections", href: "/connections" }, { label: "Connect dbt Cloud" }]} />

          <div className="form-head">
            <div className="conn-icon">DBT</div>
            <div>
              <div className="form-title">Connect dbt Cloud</div>
              <div className="form-sub">Transformation &amp; orchestration · token-based</div>
            </div>
          </div>

          <Panel>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Account">
                <div className="form-field-stack">
                  <FormField id="dbt-account" label="dbt Cloud account ID" defaultValue="47281" />
                  <FormField id="dbt-token" label="Service token" type="password" defaultValue="dbtc_••••••••••••••••" />
                </div>
              </SheetSection>

              <Alert tone="info" title="No warehouse credentials needed">
                Duster reads model tests, run metadata, and column-level lineage from dbt&rsquo;s Discovery API — it never queries
                your warehouse directly through this connection.
              </Alert>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="sheet-section-title" style={{ marginBottom: 0 }}>
                  Or connect with OAuth instead
                </div>
                <p className="form-section-hint" style={{ margin: 0 }}>
                  If your dbt Cloud plan supports it, sign in directly instead of pasting a token — the account and token fields
                  above are replaced by this single step:
                </p>
                <Button register="secondary" style={{ alignSelf: "flex-start" }}>
                  <ExternalLink size={13} aria-hidden="true" />
                  Sign in to authorize
                </Button>
              </div>
            </div>
          </Panel>

          <div className="form-footer">
            <Button register="ghost" to="/connections">Cancel</Button>
            <Button register="secondary">Test connection</Button>
            <Button register="primary">Save connection</Button>
          </div>
        </div>
      </div>
    </>
  );
}
