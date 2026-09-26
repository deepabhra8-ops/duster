import { StatusDot } from "../Badge/StatusDot.jsx";

const EM_DASH = "—";

/**
 * sources: [{ id, name, statusTone, score }]
 */
export function SourceList({ sources, selectedId, onSelect }) {
  return (
    <div className="panel-body-flush">
      {sources.map((source) => (
        <button
          key={source.id}
          type="button"
          className={`src-row${source.id === selectedId ? " is-selected" : ""}`}
          onClick={() => onSelect(source.id)}
        >
          <StatusDot tone={source.statusTone} />
          <span className="src-name">{source.name}</span>
          <span className="src-score">{source.score ?? EM_DASH}</span>
        </button>
      ))}
    </div>
  );
}

export default SourceList;
