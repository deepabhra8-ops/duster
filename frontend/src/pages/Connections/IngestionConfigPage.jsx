import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "./sectionTabs.js";
import { Alert, Breadcrumb, Button, FormField, Panel, Pill, SheetSection } from "../../design-system/components/index.js";
import { getIngestionConfig, saveIngestionConfig } from "../../api/api.js";

const LATENCY_LABEL_BY_VALUE = { real_time: "Real-time", hourly: "Hourly", daily: "Daily" };
const LATENCY_VALUE_BY_LABEL = { "Real-time": "real_time", Hourly: "hourly", Daily: "daily" };

const OWNERSHIP_LABEL_BY_VALUE = { saas: "Duster-managed", customer: "Customer-managed" };
const OWNERSHIP_VALUE_BY_LABEL = { "Duster-managed": "saas", "Customer-managed": "customer" };

const SYSTEM_TYPE_LABEL = {
  warehouse: "Warehouse",
  database: "Database",
  lake: "Data lake",
  event_stream: "Event stream",
  saas: "SaaS",
};

const MODE_LABEL = { pull: "Pull", push: "Push", poll: "Poll" };
const MODE_TONE = { pull: "success", push: "neutral", poll: "neutral" };

/**
 * Stage 2 (Ingestion Pattern Selection): classifies the connection's system type, captures
 * the two requirements (latency, scheduling ownership), and shows/persists the mode the
 * backend's decision engine computes (backend/services/ingestion_pattern_service.py). Every
 * connector Duster has today resolves to "pull" — Push/Poll are modeled for real but have no
 * connector to configure yet, so that section explains rather than fakes setup fields.
 */
export default function IngestionConfigPage() {
  const { id } = useParams();
  const formRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [connectionName, setConnectionName] = useState("");
  const [dbType, setDbType] = useState("");
  const [systemType, setSystemType] = useState("");
  const [savedConfig, setSavedConfig] = useState(null);
  const [latencyLabel, setLatencyLabel] = useState("Daily");
  const [ownershipLabel, setOwnershipLabel] = useState("Duster-managed");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const result = await getIngestionConfig(id);
      if (cancelled) return;

      if (!result.ok || !result.data?.ok) {
        setNotFound(true);
        setLoading(false);
        return;
      }

      const preview = result.data.data;
      setConnectionName(preview.connectionName);
      setDbType(preview.dbType);
      setSystemType(preview.systemType);
      setSavedConfig(preview.config);

      if (preview.config) {
        setLatencyLabel(LATENCY_LABEL_BY_VALUE[preview.config.latencyRequirement] || "Daily");
        setOwnershipLabel(OWNERSHIP_LABEL_BY_VALUE[preview.config.schedulingOwnership] || "Duster-managed");
      }

      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleSave() {
    const data = new FormData(formRef.current);
    const latencyRequirement = LATENCY_VALUE_BY_LABEL[data.get("latency")] || "daily";
    const schedulingOwnership = OWNERSHIP_VALUE_BY_LABEL[data.get("ownership")] || "saas";

    setSaving(true);
    setFeedback(null);

    const result = await saveIngestionConfig(id, latencyRequirement, schedulingOwnership);

    setSaving(false);

    if (result.ok && result.data?.ok) {
      setSavedConfig(result.data.data);
      setFeedback({ tone: "success", title: "Ingestion configured", message: "" });
    } else {
      setFeedback({ tone: "danger", title: "Couldn't save", message: result.error || result.data?.error || "Please try again." });
    }
  }

  if (loading) {
    return (
      <>
        <SectionTabs items={CONNECTIONS_SECTION_TABS} />
        <p className="connections-muted" style={{ padding: "var(--space-6)" }}>
          Loading&hellip;
        </p>
      </>
    );
  }

  if (notFound) {
    return (
      <>
        <SectionTabs items={CONNECTIONS_SECTION_TABS} />
        <p className="connections-muted" style={{ padding: "var(--space-6)" }}>
          This connection could not be found.
        </p>
      </>
    );
  }

  const mode = savedConfig?.ingestionMode;

  return (
    <>
      <SectionTabs items={CONNECTIONS_SECTION_TABS} />
      <div style={{ flex: "1 1 auto", overflowY: "auto", padding: "var(--space-6)", display: "flex", justifyContent: "center" }}>
        <div className="form-page" style={{ width: "100%", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Breadcrumb
            segments={[
              { label: "Connections", href: "/connections" },
              { label: connectionName || "Connection" },
              { label: "Ingestion" },
            ]}
          />

          <div className="form-head">
            <div className="conn-icon">{String(dbType || "").toUpperCase()}</div>
            <div>
              <div className="form-title">Configure ingestion</div>
              <div className="form-sub">{SYSTEM_TYPE_LABEL[systemType] || systemType}</div>
            </div>
          </div>

          <Panel>
            <form ref={formRef} onSubmit={(e) => e.preventDefault()} style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <SheetSection title="Requirements">
                <div className="form-field-stack">
                  <div className="sheet-field-row">
                    <FormField
                      id="ing-latency"
                      name="latency"
                      label="Latency requirement"
                      options={["Real-time", "Hourly", "Daily"]}
                      defaultValue={latencyLabel}
                    />
                    <FormField
                      id="ing-ownership"
                      name="ownership"
                      label="Scheduling ownership"
                      options={["Duster-managed", "Customer-managed"]}
                      defaultValue={ownershipLabel}
                    />
                  </div>
                </div>
              </SheetSection>

              <SheetSection title="Ingestion mode">
                {mode ? (
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Pill tone={MODE_TONE[mode]}>{MODE_LABEL[mode]}</Pill>
                    <span style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>
                      {mode === "pull"
                        ? "Duster runs this connection's checks itself on the frequency above."
                        : "Computed from this connection's system type and requirements."}
                    </span>
                  </div>
                ) : (
                  <p className="form-section-hint">Save to compute the ingestion mode for this connection.</p>
                )}

                {mode && mode !== "pull" ? (
                  <Alert tone="info" title="Not available yet">
                    {MODE_LABEL[mode]} ingestion needs a{" "}
                    {mode === "push" ? "streaming/event source" : "data-lake"} connector, and Duster
                    doesn&rsquo;t have one yet. The requirement is saved, but there&rsquo;s nothing to
                    configure here until that connector exists.
                  </Alert>
                ) : null}
              </SheetSection>

              {feedback ? <Alert tone={feedback.tone} title={feedback.title}>{feedback.message}</Alert> : null}
            </form>
          </Panel>

          <div className="form-footer">
            <Button register="ghost" to="/connections">Back to connections</Button>
            <Button register="primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
