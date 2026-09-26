import { ChartColumn, FileText, Network } from "lucide-react";
import { Pill } from "../Badge/Pill.jsx";
import { ScoreBadge } from "../ScoreBadge/ScoreBadge.jsx";
import { ResolveActions } from "../ResolveActions/ResolveActions.jsx";

const IMPACT_ICON = { report: FileText, dashboard: ChartColumn, model: Network };
const SEVERITY_TONE = { High: "danger", Medium: "warning", Low: "neutral" };

/**
 * elements: [{
 *   id, name, source, dimension, score, severity,
 *   impacts: [{ name, kind: 'report'|'dashboard'|'model' }],
 *   href,
 * }]
 */
export function CdeList({ elements }) {
  return (
    <div className="panel-body-flush">
      {elements.map((el) => (
        <CdeRow key={el.id} {...el} />
      ))}
    </div>
  );
}

function CdeRow({ name, source, dimension, score, severity, impacts, href }) {
  return (
    <div className="cde-row">
      <Pill tone={SEVERITY_TONE[severity] || "neutral"}>{severity}</Pill>
      <div className="cde-text">
        <div className="cde-name">{name}</div>
        <div className="cde-path">
          {source} &middot; {dimension}
        </div>
      </div>
      <div className="impact-group" title={`Impacts ${impacts.length} downstream asset${impacts.length === 1 ? "" : "s"}`}>
        <div className="impact-stack">
          {impacts.map((impact) => {
            const IconCmp = IMPACT_ICON[impact.kind] || FileText;
            return (
              <span key={impact.name} className="impact-icon" title={`${impact.name} (${impact.kind})`}>
                <IconCmp size={11} aria-hidden="true" />
              </span>
            );
          })}
        </div>
        <span className="impact-names">
          {impacts.map((impact, i) => (
            <span key={impact.name}>
              {i > 0 ? ", " : ""}
              {i === 0 ? <strong>{impact.name}</strong> : impact.name}
            </span>
          ))}
        </span>
      </div>
      <ScoreBadge score={score} />
      <ResolveActions lineageHref={href} />
    </div>
  );
}

export default CdeList;
