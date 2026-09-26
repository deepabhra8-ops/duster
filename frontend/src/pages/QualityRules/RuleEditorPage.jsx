import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, Plus, RefreshCw, X } from "lucide-react";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { QUALITY_RULES_SECTION_TABS } from "./sectionTabs.js";
import { Button, CodeBlock, Pill, StatusDot, TypeChip } from "../../design-system/components/index.js";
import { useRule, useRuleLibrary } from "../../hooks/useQualityRules.js";
import { useToast } from "../../hooks/useToast.js";
import { dryRunRule, duplicateRule, saveRule, setRuleEnabled, startRun } from "../../services/qualityRulesService.js";
import {
  ALL_FAMILIES,
  SCOPE_LEVELS,
  TEMPLATES,
  defaultParamsForTemplate,
  defaultThresholdForTemplate,
  templateFamilies,
  templateFamilyNote,
} from "./ruleRegistry.js";
import "./RuleEditorPage.css";

const SCOPE_LABELS = { column: "Column", table: "Table", schema: "Schema", catalog: "Catalog", all: "Everything" };

const GLOB_DEFAULTS_BY_LEVEL = {
  column: { catalog: "main", schema: "sales", table: "orders", column: "order_amount" },
  table: { catalog: "main", schema: "sales", table: "orders", column: "*_amount" },
  schema: { catalog: "main", schema: "sales*", table: "*", column: "*_amount" },
  catalog: { catalog: "main", schema: "*", table: "*", column: "*_amount" },
  all: { catalog: "*", schema: "*", table: "*", column: "*_amount" },
};

function firstRuleName(library) {
  return library?.groups?.[0]?.rules?.[0]?.name ?? null;
}

export default function RuleEditorPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { data: library, refresh: refreshLibrary } = useRuleLibrary();
  const [selectedRuleName, setSelectedRuleName] = useState(null);
  const { data: rule, refresh: refreshRule } = useRule(selectedRuleName);

  const [templateId, setTemplateId] = useState("in_range");
  const [loadedTemplateId, setLoadedTemplateId] = useState("in_range");
  const [params, setParams] = useState(() => defaultParamsForTemplate("in_range"));
  const [threshold, setThreshold] = useState(() => defaultThresholdForTemplate("in_range"));
  const [severity, setSeverity] = useState("error");
  const [weight, setWeight] = useState(1.0);
  const [nulls, setNulls] = useState("ignore");
  const [rowFilter, setRowFilter] = useState("");
  const [scopeLevel, setScopeLevel] = useState("schema");
  const [glob, setGlob] = useState(GLOB_DEFAULTS_BY_LEVEL.schema);
  const [exclude, setExclude] = useState([]);
  const [excludeDraft, setExcludeDraft] = useState("");
  const [tableTypes, setTableTypes] = useState({ managed: true, external: true, view: false });
  const [plan, setPlan] = useState(null);
  const [planStatus, setPlanStatus] = useState({ loading: false, error: null });
  const [runOptions, setRunOptions] = useState({ where: "", sampleFraction: "", maxParallelTables: "4" });
  const [busy, setBusy] = useState(false);

  // Open the first rule once the library arrives. Only while nothing is selected: a
  // freshly duplicated rule isn't in the (still refreshing) library yet.
  useEffect(() => {
    if (library && selectedRuleName === null) setSelectedRuleName(firstRuleName(library));
  }, [library, selectedRuleName]);

  const planFor = useCallback(async (draft) => {
    setPlanStatus({ loading: true, error: null });
    const result = await dryRunRule(draft);

    if (!result.ok) {
      setPlanStatus({ loading: false, error: result.error });
      return;
    }

    setPlan(result.data);
    setLoadedTemplateId(draft.template);
    setPlanStatus({ loading: false, error: null });
  }, []);

  useEffect(() => {
    if (!rule) return;
    setTemplateId(rule.template);
    setLoadedTemplateId(rule.template);
    setParams(rule.params);
    setThreshold(rule.threshold);
    setSeverity(rule.severity);
    setWeight(rule.weight);
    setNulls(rule.nullPolicy);
    setRowFilter(rule.rowFilter);
    setScopeLevel(rule.scope.level);
    setGlob({ catalog: rule.scope.catalog, schema: rule.scope.schema, table: rule.scope.table, column: rule.scope.column });
    setExclude(rule.exclude);
    setTableTypes(rule.tableTypes);
    planFor(rule);
  }, [rule, planFor]);

  function currentDraft() {
    return {
      ...rule,
      template: templateId,
      params,
      threshold,
      severity,
      weight,
      nullPolicy: nulls,
      rowFilter,
      scope: { level: scopeLevel, ...glob },
      exclude,
      tableTypes,
    };
  }

  async function act(work, successTitle) {
    setBusy(true);
    const result = await work();
    setBusy(false);

    if (!result.ok) {
      showToast({ type: "error", title: "Couldn't complete that", message: result.error });
      return null;
    }

    if (successTitle) showToast({ type: "success", title: successTitle });
    return result.data;
  }

  async function handleSave() {
    const saved = await act(() => saveRule(currentDraft()), "Rule saved");
    if (!saved) return;
    refreshRule();
    refreshLibrary();
  }

  async function handleToggleEnabled() {
    const saved = await act(() => setRuleEnabled(rule.ruleId, !rule.enabled), rule.enabled ? "Rule disabled" : "Rule enabled");
    if (!saved) return;
    refreshRule();
    refreshLibrary();
  }

  async function handleDuplicate() {
    const copy = await act(() => duplicateRule(rule.ruleId), "Rule duplicated");
    if (!copy) return;
    refreshLibrary();
    setSelectedRuleName(copy.name);
  }

  async function handleRun() {
    const run = await act(() => startRun({ ruleIds: [rule.ruleId], ...runOptions }), "Run started");
    if (run) navigate("/quality-rules/runs");
  }

  function pickTemplate(id) {
    setTemplateId(id);
    setParams(defaultParamsForTemplate(id));
    setThreshold(defaultThresholdForTemplate(id));
  }

  function pickScopeLevel(level) {
    setScopeLevel(level);
    setGlob(GLOB_DEFAULTS_BY_LEVEL[level]);
  }

  function addExclude() {
    const pattern = excludeDraft.trim();
    if (!pattern || exclude.includes(pattern)) return;
    setExclude((list) => [...list, pattern]);
    setExcludeDraft("");
  }

  function removeExclude(pattern) {
    setExclude((list) => list.filter((p) => p !== pattern));
  }

  const stale = templateId !== loadedTemplateId;
  const families = templateFamilies(templateId);
  const familyNote = templateFamilyNote(templateId);

  return (
    <>
      <SectionTabs
        items={QUALITY_RULES_SECTION_TABS}
        right={library ? <span>{library.totalRules} rules · {library.failingCount} failing · last run {library.lastRunLabel}</span> : null}
      />

      <div className="rule-editor-page">
        <RuleLibrary library={library} selectedRuleName={selectedRuleName} onSelect={setSelectedRuleName} />

        <main className="rule-editor-main">
          <RuleHead
            rule={rule}
            busy={busy}
            onSave={handleSave}
            onToggleEnabled={handleToggleEnabled}
            onDuplicate={handleDuplicate}
          />

          <section className="panel">
            <div className="panel-header">
              <div className="panel-title-group">
                <span className="panel-title">Template</span>
                <span className="caption">What to measure. Pick one from the registry, then set its parameters.</span>
              </div>
              <Button register="ghost" size="xs">Browse registry</Button>
            </div>
            <div className="panel-body">
              <div className="dq-tpl-grid">
                {TEMPLATES.map((tpl) => (
                  <button
                    key={tpl.id}
                    type="button"
                    className={`dq-tpl-card${tpl.id === templateId ? " is-selected" : ""}`}
                    aria-pressed={tpl.id === templateId}
                    onClick={() => pickTemplate(tpl.id)}
                  >
                    <span className="dq-tpl-name">{tpl.name}</span>
                    <span className="dq-tpl-meta">
                      <span className="dq-tpl-dim">{tpl.dimension}</span>
                      <TypeChip>{tpl.level}</TypeChip>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div className="panel-title-group">
                <span className="panel-title">Parameters &amp; pass criteria</span>
                <span className="caption ds-mono">{templateId}</span>
              </div>
            </div>
            <div className="panel-body rule-editor-params-body">
              <TemplateParamsForm templateId={templateId} params={params} onChange={setParams} />

              <div className="dq-fam-row">
                <span className="field-label" style={{ margin: "0 6px 0 0" }}>Applies to</span>
                {ALL_FAMILIES.map((fam) => (
                  <span key={fam} className={`dq-fam-chip${families.includes(fam) ? " is-on" : ""}`}>{fam}</span>
                ))}
                <span className="caption" style={{ marginLeft: 6 }}>{familyNote}</span>
              </div>

              <div className="dq-divider" />

              <div className="dq-form-grid">
                <div className="dq-span-2">
                  <ThresholdRow templateId={templateId} threshold={threshold} onChange={setThreshold} />
                </div>
                <div>
                  <span className="field-label">Severity</span>
                  <div className="dq-seg" role="group" aria-label="Severity">
                    {["info", "warn", "error"].map((s) => (
                      <button
                        key={s}
                        type="button"
                        className={`dq-seg-btn${severity === s ? " is-on" : ""}`}
                        aria-pressed={severity === s}
                        onClick={() => setSeverity(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="field-label" htmlFor="weight">Weight</label>
                  <input id="weight" className="field-input" value={weight} onChange={(e) => setWeight(e.target.value)} />
                </div>
              </div>

              <div className="dq-form-grid">
                <div>
                  <span className="field-label">Nulls</span>
                  <div className="dq-seg" role="group" aria-label="Null policy">
                    {[["ignore", "Pass"], ["fail", "Fail"]].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={`dq-seg-btn${nulls === value ? " is-on" : ""}`}
                        aria-pressed={nulls === value}
                        onClick={() => setNulls(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="dq-span-3">
                  <label className="field-label" htmlFor="row-filter">
                    Row filter <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}>&mdash; only matching rows count toward the total</span>
                  </label>
                  <input
                    id="row-filter"
                    className="field-input"
                    placeholder="order_status <> 'cancelled'"
                    value={rowFilter}
                    onChange={(e) => setRowFilter(e.target.value)}
                  />
                </div>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div className="panel-title-group">
                <span className="panel-title">Scope</span>
                <span className="caption">Where the rule runs by default. A run can override it.</span>
              </div>
              <div className="dq-seg dq-seg-sm" role="group" aria-label="Scope level">
                {SCOPE_LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`dq-seg-btn${scopeLevel === level ? " is-on" : ""}`}
                    aria-pressed={scopeLevel === level}
                    onClick={() => pickScopeLevel(level)}
                  >
                    {SCOPE_LABELS[level]}
                  </button>
                ))}
              </div>
            </div>
            <div className="panel-body rule-editor-params-body">
              <div className="dq-glob-grid">
                {["catalog", "schema", "table", "column"].map((field) => (
                  <div key={field}>
                    <label className="field-label" htmlFor={`glob-${field}`}>{field}</label>
                    <input
                      id={`glob-${field}`}
                      className="field-input"
                      value={glob[field]}
                      onChange={(e) => setGlob((g) => ({ ...g, [field]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>

              <div className="dq-form-grid" style={{ alignItems: "start" }}>
                <div className="dq-span-2">
                  <label className="field-label" htmlFor="exclude-add">Exclude</label>
                  <div className="dq-chip-input">
                    {exclude.map((pattern) => (
                      <span key={pattern} className="dq-x-chip">
                        {pattern}
                        <button type="button" aria-label={`Remove ${pattern}`} onClick={() => removeExclude(pattern)}>
                          <X size={9} strokeWidth={3} aria-hidden="true" />
                        </button>
                      </span>
                    ))}
                    <input
                      id="exclude-add"
                      placeholder="Add pattern"
                      value={excludeDraft}
                      onChange={(e) => setExcludeDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addExclude();
                        }
                      }}
                    />
                  </div>
                </div>
                <div className="dq-span-2">
                  <span className="field-label">Table types &amp; tags</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 14, minHeight: 32, flexWrap: "wrap" }}>
                    {["managed", "external", "view"].map((kind) => (
                      <label key={kind} className="dq-check">
                        <input
                          type="checkbox"
                          checked={tableTypes[kind]}
                          onChange={(e) => setTableTypes((t) => ({ ...t, [kind]: e.target.checked }))}
                        />
                        {kind}
                      </label>
                    ))}
                    <button type="button" className="dq-dash-btn">
                      <Plus size={10} strokeWidth={2.6} aria-hidden="true" />
                      Tag filter
                    </button>
                  </div>
                </div>
              </div>

              <p className="hint">
                <code>*</code> matches any run of characters and <code>?</code> matches one. Tables resolve from{" "}
                <code>information_schema</code>; columns are re-checked against each table&rsquo;s live schema when the run starts.
              </p>
            </div>
          </section>
        </main>

        <DryRunPlan
          plan={plan}
          status={planStatus}
          stale={stale}
          loadedTemplateId={loadedTemplateId}
          templateId={templateId}
          runOptions={runOptions}
          onRunOptionsChange={setRunOptions}
          onDryRun={() => planFor(currentDraft())}
          onRun={handleRun}
          canRun={Boolean(rule) && !busy}
        />
      </div>
    </>
  );
}

function RuleLibrary({ library, selectedRuleName, onSelect }) {
  return (
    <aside className="panel rule-library" aria-label="Rule library">
      <div className="panel-header">
        <span className="panel-title">Rules</span>
        <Button register="secondary" size="xs">
          <Plus size={11} strokeWidth={2.6} aria-hidden="true" />
          New rule
        </Button>
      </div>
      <div className="rule-library-search">
        <label htmlFor="rule-filter" className="sr-only">Filter rules</label>
        <div className="search-field" style={{ width: "100%" }}>
          <input id="rule-filter" type="text" placeholder="Filter by name, template, table" />
        </div>
      </div>
      <div className="rule-library-list">
        {(library?.groups || []).map((group) => (
          <div key={group.dimension}>
            <div className="dq-group-head">
              {group.dimension}
              <span>{group.rules.length}</span>
            </div>
            {group.rules.map((r) => (
              <button
                key={r.name}
                type="button"
                className={`dq-rule-row${r.name === selectedRuleName ? " is-selected" : ""}${r.disabled ? " is-off" : ""}`}
                aria-current={r.name === selectedRuleName || undefined}
                onClick={() => onSelect(r.name)}
              >
                <StatusDot tone={r.statusTone} />
                <span className="dq-rule-name">{r.name}</span>
                <span className="dq-rule-id">{r.disabled ? "off" : r.ruleId}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

function RuleHead({ rule, busy, onSave, onToggleEnabled, onDuplicate }) {
  if (!rule) return null;
  const { lastRun } = rule;
  return (
    <>
      <div className="rule-editor-head">
        <div className="rule-editor-head-text">
          <div className="crumb">
            <Link to="/quality-rules" className="crumb-link">Rules</Link>
            <span className="crumb-sep">/</span>
            <span className="crumb-current">{rule.name}</span>
            <TypeChip>{rule.ruleId} · v{rule.version}</TypeChip>
          </div>
          {rule.description ? <p className="rule-editor-desc">{rule.description}</p> : null}
        </div>
        <div className="rule-editor-actions">
          <Button register="ghost" size="xs" onClick={onDuplicate} disabled={busy}>Duplicate</Button>
          <Button register="secondary" size="xs" onClick={onToggleEnabled} disabled={busy}>
            {rule.enabled === false ? "Enable" : "Disable"}
          </Button>
          <Button register="primary" size="xs" onClick={onSave} disabled={busy}>Save rule</Button>
        </div>
      </div>

      <div className="rule-editor-lastrun">
        <span className="caption" style={{ marginRight: 4 }}>
          Last run <span className="ds-mono">{lastRun.atLabel}</span>
        </span>
        <Pill tone="danger">{lastRun.fail} fail</Pill>
        <Pill tone="success">{lastRun.pass} pass</Pill>
        <Pill tone="neutral">{lastRun.noData} no data</Pill>
        <Pill tone="neutral">{lastRun.skipped} skipped</Pill>
        <Link to="/quality-rules/runs" className="rule-editor-view-run">View run &rarr;</Link>
      </div>
    </>
  );
}

function TemplateParamsForm({ templateId, params, onChange }) {
  function set(key, value) {
    onChange({ ...params, [key]: value });
  }

  const sampling = (label, tone) => (
    <div>
      <span className="field-label">Sampling</span>
      <div className="dq-readout">
        <StatusDot tone={tone} />
        {label}
      </div>
    </div>
  );

  switch (templateId) {
    case "not_null":
      return (
        <div className="dq-form-grid">
          <div className="dq-note-cell dq-span-3">No parameters. A null always fails this check, so the null policy below doesn&rsquo;t apply.</div>
          {sampling("Full scan only", "idle")}
        </div>
      );
    case "not_blank":
      return (
        <div className="dq-form-grid">
          <div className="dq-note-cell dq-span-3">No parameters. Passes when the value is non-null and contains something other than whitespace.</div>
          {sampling("Sample-safe", "success")}
        </div>
      );
    case "in_range":
      return (
        <div className="dq-form-grid">
          <div>
            <label className="field-label" htmlFor="ir-min">Min</label>
            <input id="ir-min" className="field-input" value={params.min} onChange={(e) => set("min", e.target.value)} />
          </div>
          <div>
            <label className="field-label" htmlFor="ir-max">Max</label>
            <input id="ir-max" className="field-input" value={params.max} onChange={(e) => set("max", e.target.value)} />
          </div>
          <div>
            <span className="field-label">Bounds</span>
            <div className="dq-seg" role="group" aria-label="Bounds">
              <button type="button" className={`dq-seg-btn${params.boundsInclusive ? " is-on" : ""}`} onClick={() => set("boundsInclusive", true)}>Inclusive</button>
              <button type="button" className={`dq-seg-btn${!params.boundsInclusive ? " is-on" : ""}`} onClick={() => set("boundsInclusive", false)}>Exclusive</button>
            </div>
          </div>
          {sampling("Sample-safe", "success")}
        </div>
      );
    case "allowed_values":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="dq-form-grid">
            <div className="dq-span-2">
              <label className="field-label" htmlFor="av-values">Values</label>
              <input id="av-values" className="field-input" value={params.values} onChange={(e) => set("values", e.target.value)} />
            </div>
            <div>
              <span className="field-label">Match</span>
              <div className="dq-seg" role="group" aria-label="Match">
                <button type="button" className={`dq-seg-btn${params.matchCase ? " is-on" : ""}`} onClick={() => set("matchCase", true)}>Exact</button>
                <button type="button" className={`dq-seg-btn${!params.matchCase ? " is-on" : ""}`} onClick={() => set("matchCase", false)}>Ignore case</button>
              </div>
            </div>
            {sampling("Sample-safe", "success")}
          </div>
          <p className="hint">Lists longer than about 200 values run as a join against a reference table instead of <code>isin</code>.</p>
        </div>
      );
    case "regex_match":
      return (
        <div className="dq-form-grid">
          <div className="dq-span-2">
            <label className="field-label" htmlFor="rx-pattern">Pattern</label>
            <input id="rx-pattern" className="field-input" value={params.pattern} onChange={(e) => set("pattern", e.target.value)} />
          </div>
          <div>
            <span className="field-label">Match</span>
            <div className="dq-seg" role="group" aria-label="Match">
              <button type="button" className={`dq-seg-btn${params.fullValue ? " is-on" : ""}`} onClick={() => set("fullValue", true)}>Full value</button>
              <button type="button" className={`dq-seg-btn${!params.fullValue ? " is-on" : ""}`} onClick={() => set("fullValue", false)}>Contains</button>
            </div>
          </div>
          {sampling("Sample-safe", "success")}
        </div>
      );
    case "unique_ratio":
      return (
        <div className="dq-form-grid">
          <div>
            <span className="field-label">Counting</span>
            <div className="dq-seg" role="group" aria-label="Counting">
              <button type="button" className={`dq-seg-btn${!params.exact ? " is-on" : ""}`} onClick={() => set("exact", false)}>Approximate</button>
              <button type="button" className={`dq-seg-btn${params.exact ? " is-on" : ""}`} onClick={() => set("exact", true)}>Exact</button>
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="ur-rsd">Max rel. std. dev.</label>
            <input id="ur-rsd" className="field-input" value={params.maxRsd} onChange={(e) => set("maxRsd", e.target.value)} />
          </div>
          <div className="dq-note-cell dq-span-2">Distinct &divide; non-null count, using HyperLogLog++. Below 0.01, an exact <code>count_distinct</code> costs less.</div>
        </div>
      );
    case "freshness_hours":
      return (
        <div className="dq-form-grid">
          <div>
            <span className="field-label">Measured against</span>
            <button type="button" className="dq-select-btn" style={{ width: "100%" }} aria-haspopup="listbox">
              {params.measuredAgainst}
              <ChevronDown size={11} strokeWidth={2.6} aria-hidden="true" />
            </button>
          </div>
          <div className="dq-note-cell dq-span-2">Hours between now and <code>max(column)</code>. Point the scope at a load or update timestamp.</div>
          {sampling("Full scan only", "idle")}
        </div>
      );
    case "row_count":
      return (
        <div className="dq-form-grid">
          <div className="dq-note-cell dq-span-3">Table-level. Counts rows once per table; the scope&rsquo;s column pattern is ignored.</div>
          {sampling("Full scan only", "idle")}
        </div>
      );
    case "referential_integrity":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="dq-form-grid">
            <div className="dq-span-2">
              <label className="field-label" htmlFor="ri-table">Parent table</label>
              <input id="ri-table" className="field-input" value={params.parentTable} onChange={(e) => set("parentTable", e.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="ri-col">Parent column</label>
              <input id="ri-col" className="field-input" value={params.parentColumn} onChange={(e) => set("parentColumn", e.target.value)} />
            </div>
            {sampling("Full scan only", "idle")}
          </div>
          <p className="hint">Needs a join, so it runs as its own job instead of sharing the table scan. Null keys are excluded from the total.</p>
        </div>
      );
    case "sql_row":
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div>
            <label className="field-label" htmlFor="sql-expr">Expression</label>
            <textarea id="sql-expr" className="field-input dq-textarea" value={params.expression} onChange={(e) => set("expression", e.target.value)} />
          </div>
          <p className="hint">
            <code>{"{column}"}</code> is replaced with the quoted column name. The expression must return BOOLEAN; it&rsquo;s
            analysed against each table before the scan runs.
          </p>
        </div>
      );
    default:
      return null;
  }
}

const THRESHOLD_METRIC_LABEL = { pass_rate: "pass_rate", value: "value" };
const THRESHOLD_OP_SYMBOL = { ">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=" };

function ThresholdRow({ threshold, onChange }) {
  return (
    <>
      <label className="field-label" htmlFor="th-value">Pass when</label>
      <div className="dq-th-row">
        <button type="button" className="dq-select-btn" aria-haspopup="listbox">
          {THRESHOLD_METRIC_LABEL[threshold.metric] || threshold.metric}
          <ChevronDown size={11} strokeWidth={2.6} aria-hidden="true" />
        </button>
        <button type="button" className="dq-select-btn" aria-haspopup="listbox">
          {THRESHOLD_OP_SYMBOL[threshold.op] || threshold.op}
          <ChevronDown size={11} strokeWidth={2.6} aria-hidden="true" />
        </button>
        <input
          id="th-value"
          className="field-input"
          style={{ width: 84 }}
          value={threshold.value}
          onChange={(e) => onChange({ ...threshold, value: e.target.value })}
        />
        <span className="dq-unit">{threshold.unit}</span>
      </div>
    </>
  );
}

function DryRunPlan({
  plan,
  status,
  stale,
  loadedTemplateId,
  templateId,
  runOptions,
  onRunOptionsChange,
  onDryRun,
  onRun,
  canRun,
}) {
  function setOption(key, value) {
    onRunOptionsChange((options) => ({ ...options, [key]: value }));
  }

  return (
    <aside className="panel rule-editor-plan" aria-label="Dry-run plan">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title">Dry-run plan</span>
          <span className="caption">No data scanned</span>
        </div>
        <Button register="secondary" size="xs" onClick={onDryRun} disabled={status.loading}>
          <RefreshCw size={11} strokeWidth={2.4} aria-hidden="true" />
          Dry run
        </Button>
      </div>

      <div className="rule-editor-plan-scroll">
        {status.error ? (
          <div style={{ padding: "12px 16px 0" }}>
            <div className="dalert dalert-warning" role="alert">
              <span>{status.error}</span>
            </div>
          </div>
        ) : null}

        {stale && plan ? (
          <div style={{ padding: "12px 16px 0" }}>
            <div className="dalert dalert-warning" role="status">
              <span>
                This plan was built for <strong className="ds-mono">{loadedTemplateId}</strong>. Run a dry run again to see how{" "}
                <strong className="ds-mono">{templateId}</strong> binds.
              </span>
            </div>
          </div>
        ) : null}

        {plan ? null : (
          <div className="dq-plan-more">{status.loading ? "Resolving scope…" : "Run a dry run to see how this rule binds."}</div>
        )}

        {plan ? <PlanBody plan={plan} /> : null}

        <div className="dq-plan-head" style={{ paddingTop: 16 }}>Run options</div>
        <div className="rule-editor-run-options">
          <div>
            <label className="field-label" htmlFor="run-where">Incremental predicate</label>
            <input
              id="run-where"
              className="field-input"
              placeholder="event_date = current_date() - 1"
              value={runOptions.where}
              onChange={(e) => setOption("where", e.target.value)}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
            <div>
              <label className="field-label" htmlFor="run-sample">Sample fraction</label>
              <input
                id="run-sample"
                className="field-input"
                placeholder="off"
                value={runOptions.sampleFraction}
                onChange={(e) => setOption("sampleFraction", e.target.value)}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="run-par">Parallel tables</label>
              <input
                id="run-par"
                className="field-input"
                value={runOptions.maxParallelTables}
                onChange={(e) => setOption("maxParallelTables", e.target.value)}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="rule-editor-plan-footer">
        <span className="caption">Results append to <span className="ds-mono" style={{ color: "var(--ink)" }}>main.dq.results</span></span>
        <Button register="primary" onClick={onRun} disabled={!canRun}>{plan ? plan.runLabel : "Run"}</Button>
      </div>
    </aside>
  );
}

function PlanBody({ plan }) {
  return (
    <>
      <div className="dq-plan-stats">
        <div className="dq-plan-stat"><span className="dq-plan-num">{plan.tables}</span><span className="caption">tables</span></div>
        <div className="dq-plan-stat"><span className="dq-plan-num">{plan.bindings}</span><span className="caption">bindings</span></div>
        <div className="dq-plan-stat"><span className={`dq-plan-num${plan.skipped !== "0" ? " is-warn" : ""}`}>{plan.skipped}</span><span className="caption">skipped</span></div>
        <div className="dq-plan-stat"><span className="dq-plan-num">{plan.excluded}</span><span className="caption">excluded</span></div>
      </div>

      <div className="dq-plan-head">Resolved tables <span>bindings</span></div>
      {plan.rows.map((row) => (
        <div key={row.table} className="dq-plan-row">
          <div className="dq-plan-row-top">
            <span className="dq-plan-fqn">{row.table}</span>
            <span className="dq-plan-n">{row.count}</span>
          </div>
          <span className="dq-plan-cols">{row.columns}</span>
        </div>
      ))}
      {plan.moreTables ? <div className="dq-plan-more">{plan.moreTables}</div> : null}

      <div className="dq-plan-head">Skipped columns <span>type doesn&rsquo;t fit</span></div>
      {plan.skips.map((skip) => (
        <div key={skip.column} className="dq-skip-row">
          <span className="dq-skip-col">{skip.column}</span>
          <span className="dq-skip-why">{skip.reason}</span>
        </div>
      ))}
      {plan.moreSkips ? <div className="dq-plan-more">{plan.moreSkips}</div> : null}
      {!plan.skips.length ? <div className="dq-plan-more">Every matched column fits the template.</div> : null}

      {plan.problems.length ? (
        <>
          <div className="dq-plan-head">Can&rsquo;t plan <span>fix before running</span></div>
          {plan.problems.map((problem) => (
            <div key={problem} className="dq-skip-row">
              <span className="dq-skip-why">{problem}</span>
            </div>
          ))}
        </>
      ) : null}

      <div className="dq-plan-head" style={{ paddingTop: 16 }}>{plan.scanOf} <span>one aggregate pass per table</span></div>
      <CodeBlock sql={plan.sql} />
    </>
  );
}
