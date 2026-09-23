import { useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import RuleExampleCards from "../components/RuleExampleCards.jsx";
import { DQ_RULES, SCORE_LEGEND, dimensionSlug, ruleDimensions } from "../constants/dqRules.js";
import { PAGE_META } from "../constants/appConfig.js";
import { IconCheck, IconWarning, IconError } from "../components/Icons.jsx";
import LovUploadPanel from "../components/LovUploadPanel.jsx";

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

  if (dimensionParam && !dimension) return <Navigate to="/rules" replace />;

  const meta = PAGE_META.rules;

  return (
    <section>
      <header className="page-header">
        <h2>{meta.title}</h2>
        <p>{meta.subtitle}</p>
      </header>

      <div className="card rules-placeholder-examples">
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
