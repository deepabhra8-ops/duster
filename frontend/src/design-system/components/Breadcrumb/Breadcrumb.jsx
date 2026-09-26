import { Link } from "react-router-dom";
import { ScoreBadge } from "../ScoreBadge/ScoreBadge.jsx";

/**
 * segments: [{ label, href, icon? }], the last segment is the current level.
 * currentScore: score to show inline next to the current segment, only meaningful at column level.
 */
export function Breadcrumb({ segments, currentScore }) {
  const last = segments[segments.length - 1];
  const ancestors = segments.slice(0, -1);

  return (
    <nav className="crumb" aria-label="Schema breadcrumb">
      {ancestors.map((seg, i) => (
        <span key={seg.href || seg.label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Link to={seg.href || "#"} className="crumb-link">
            {seg.icon || null}
            {seg.label}
          </Link>
          <span className="crumb-sep">/</span>
        </span>
      ))}
      <span className="crumb-current">
        {last?.label}
        {currentScore !== undefined ? <ScoreBadge score={currentScore} /> : null}
      </span>
    </nav>
  );
}

export default Breadcrumb;
