/**
 * Rules.jsx - DQ Rule Reference page.
 *
 * Source of rules: there is no rules API in the backend or API layer, so
 * rules load from constants/dqRules.js (DQ_RULES). If a rules endpoint is
 * added later, swap the `loadRules` body to call it - the rest of the page
 * (search / filter) is source-agnostic.
 *
 * Features: search, dimension filter, plus the score-threshold legend.
 *
 * The dimension filter lives in the URL (/rules/:dimension), not in state: the
 * second-tier sidebar links to those routes, and the toolbar dropdown navigates
 * to them, so the two controls cannot disagree. An unknown dimension in the URL
 * falls back to the full list.
 */
import { useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import RuleExampleCards from "../components/RuleExampleCards.jsx";
import { DQ_RULES, SCORE_LEGEND, dimensionSlug, ruleDimensions } from "../constants/dqRules.js";
import { PAGE_META } from "../constants/appConfig.js";
import { IconCheck, IconWarning, IconError } from "../components/Icons.jsx";
import LovUploadPanel from "../components/LovUploadPanel.jsx";

/** Rules source - constants today; swap for an API call if one is added. */
function loadRules() {
  return DQ_RULES;
}

export default function Rules() {
  const allRules = useMemo(() => loadRules(), []);

  const navigate = useNavigate();
  const { dimension: dimensionParam } = useParams();
  const [search, setSearch] = useState("");

  const dimensions = useMemo(() => ruleDimensions(allRules), [allRules]);
  const dimension = dimensions.find((d) => dimensionSlug(d) === dimensionParam) ?? "";

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRules.filter((r) => {
      if (dimension && r.dim !== dimension) return false;
      if (!q) return true;
      return [r.id, r.dim, r.cat, r.desc, r.params].some((v) => String(v).toLowerCase().includes(q));
    });
  }, [allRules, search, dimension]);

  // After every hook: a URL naming a dimension that does not exist is not a
  // page of its own, so send it to the full list rather than an empty one.
  if (dimensionParam && !dimension) return <Navigate to="/rules" replace />;

  const meta = PAGE_META.rules;

  return (
    <section>
      <header className="page-header">
        <h2>{meta.title}</h2>
        <p>{meta.subtitle}</p>
      </header>

      <div className="card rules-placeholder-examples">
        {/* Toolbar */}
        <div className="uploads-toolbar rules-toolbar">
          <input
            type="text"
            className="search-input"
            placeholder="Search rules…"
            autoComplete="off"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="filter-select"
            value={dimension}
            onChange={(e) =>
              navigate(e.target.value ? `/rules/${dimensionSlug(e.target.value)}` : "/rules")
            }
          >
            <option value="">All Dimensions</option>
            {dimensions.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>

          {/* Score thresholds legend, at the right end of the toolbar */}
          <div className="rules-score-group">
            <span className="rules-score-label">Score Threshold</span>
            <div className="score-grid score-grid-compact">
              {SCORE_LEGEND.map((s) => (
                <div key={s.label} className={`score-card score-card-compact ${s.cls}`}>
                  <div className="score-card-text">
                    <div className="dim">{s.label}</div>
                    <div className="val">{s.range}</div>
                  </div>
                  <div className="rag">{s.cls === "sc-good" ? <IconCheck /> : s.cls === "sc-warn" ? <IconWarning /> : <IconError />}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card-title">Examples and expected results</div>
        <p className="hint">
          Enter the example text in the rule's Parameters field. A passing result means the value meets the rule; otherwise it is listed as a failed value in the validation output.
        </p>
        <RuleExampleCards examples={filtered.filter((rule) => rule.example)} />
      </div>
    </section>
  );
}
