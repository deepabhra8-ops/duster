import { ScoreBadge } from "../ScoreBadge/ScoreBadge.jsx";
import { TypeChip } from "../Badge/TypeChip.jsx";

const CARET = (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
    <path d="M9 6l6 6-6 6" />
  </svg>
);

/**
 * node: { id, kind: 'database'|'schema'|'table'|'column', name, icon, meta, score, typeChip, children, isOpen, isSelected }
 * A column node is a leaf: no caret slot is rendered as empty rather than collapsed, so every
 * row's name starts at the same x-position regardless of depth (per the SchemaTree spec).
 */
export function SchemaTree({ nodes, depth = 0, onSelect }) {
  return (
    <div className="tree">
      {nodes.map((node) => (
        <SchemaTreeRow key={node.id} node={node} depth={depth} onSelect={onSelect} />
      ))}
    </div>
  );
}

function SchemaTreeRow({ node, depth, onSelect }) {
  const isBranch = node.kind !== "column";
  const showScore = node.kind === "table" || node.kind === "column";

  return (
    <>
      <div
        className={`tree-row${node.isOpen ? " is-open" : ""}${node.isSelected ? " is-selected" : ""}`}
        style={{ "--depth-pad": `${8 + depth * 16}px` }}
        onClick={() => onSelect?.(node)}
      >
        <span className="tree-caret">{isBranch ? CARET : null}</span>
        <span className="tree-icon">{node.icon}</span>
        <span className="tree-name">{node.name}</span>
        {node.typeChip ? <TypeChip>{node.typeChip}</TypeChip> : null}
        {showScore && node.score !== undefined ? (
          <ScoreBadge score={node.score} />
        ) : node.meta ? (
          <span className="tree-meta">{node.meta}</span>
        ) : null}
      </div>
      {node.isOpen && node.children?.length ? (
        <div className="tree-children">
          <SchemaTree nodes={node.children} depth={depth + 1} onSelect={onSelect} />
        </div>
      ) : null}
    </>
  );
}

export default SchemaTree;
