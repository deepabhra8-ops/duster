import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { Sheet } from "../../design-system/components/index.js";
import { CONNECTOR_CATEGORIES, connectorsByCategory, popularConnectors } from "./connectorCatalog.js";

/**
 * The "Add connection" catalog sheet — a wide (720px) rail + tile grid, replacing the old
 * narrow single-connector sheet. Defaults to "Popular"; picking a category on the left shows
 * that category's tiles. Clicking an available tile navigates to its dedicated connector form
 * page; a coming-soon tile is disabled rather than routed to a mismatched form.
 */
export function AddConnectionSheet({ isOpen, onClose }) {
  const navigate = useNavigate();
  const [rail, setRail] = useState("Popular");
  const [search, setSearch] = useState("");

  const tiles = useMemo(() => {
    const base = rail === "Popular" ? popularConnectors() : connectorsByCategory(rail);
    const q = search.trim().toLowerCase();
    return q ? base.filter((c) => c.name.toLowerCase().includes(q)) : base;
  }, [rail, search]);

  function handleTileClick(connector) {
    if (connector.status !== "available") return;
    onClose();
    navigate(connector.route);
  }

  return (
    <Sheet isOpen={isOpen} onClose={onClose} title="Add a connection" wide bodyClassName="sheet-body-split"
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <span style={{ fontSize: 11, color: "var(--ink-faint)" }}>
            Pick a source to continue, or browse a category on the left
          </span>
        </>
      }
    >
      <div className="catalog-rail">
        <div className="catalog-rail-search">
          <Search aria-hidden="true" />
          <input
            type="text"
            placeholder="Search sources…"
            aria-label="Search sources"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="catalog-rail-nav">
          <button
            type="button"
            className={`catalog-rail-item${rail === "Popular" ? " is-active" : ""}`}
            onClick={() => setRail("Popular")}
          >
            <span>Popular</span>
            <span className="catalog-rail-item-count">{popularConnectors().length}</span>
          </button>
          {CONNECTOR_CATEGORIES.map((category) => (
            <button
              key={category}
              type="button"
              className={`catalog-rail-item${rail === category ? " is-active" : ""}`}
              onClick={() => setRail(category)}
            >
              <span>{category}</span>
              <span className="catalog-rail-item-count">{connectorsByCategory(category).length}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="catalog-panel">
        <div className="catalog-panel-title">{rail}</div>
        <div className="catalog-grid-v2">
          {tiles.map((connector) => (
            <button
              key={connector.id}
              type="button"
              className={`catalog-tile-v2${connector.status !== "available" ? " is-disabled" : ""}`}
              onClick={() => handleTileClick(connector)}
              disabled={connector.status !== "available"}
              title={connector.status !== "available" ? "Coming soon" : undefined}
            >
              <span className="catalog-tile-icon">{connector.icon}</span>
              <span className="catalog-tile-name-v2">{connector.name}</span>
              <span className="catalog-tile-caption">{connector.status === "available" ? connector.caption : "Coming soon"}</span>
            </button>
          ))}
          {!tiles.length ? (
            <p style={{ gridColumn: "1 / -1", fontSize: 12.5, color: "var(--ink-muted)" }}>
              No sources match &ldquo;{search}&rdquo;.
            </p>
          ) : null}
        </div>
      </div>
    </Sheet>
  );
}

export default AddConnectionSheet;
