import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, Plus, RefreshCw, SlidersHorizontal } from "lucide-react";
import SectionTabs from "../../layout/AppShell/SectionTabs.jsx";
import { CONNECTIONS_SECTION_TABS } from "./sectionTabs.js";
import { Button, CategoryToolbar, Panel, StatusRow, Table, TableEmpty } from "../../design-system/components/index.js";
import { useConnectionsList } from "../../hooks/useConnectionsList.js";
import { heartbeatConnection } from "../../api/api.js";
import { AddConnectionSheet } from "./AddConnectionSheet.jsx";
import { EditConnectionSheet } from "./EditConnectionSheet.jsx";
import { CONNECTOR_CATALOG, CONNECTOR_CATEGORIES } from "./connectorCatalog.js";
import "./ConnectionsPage.css";

export default function ConnectionsPage() {
  const navigate = useNavigate();
  const { data, loading, revalidate } = useConnectionsList();
  const [activeCategory, setActiveCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const connections = data ?? [];

  const categories = useMemo(
    () => CONNECTOR_CATEGORIES.filter((category) => connections.some((c) => c.category === category)),
    [connections]
  );

  const needsAttention = connections.filter((c) => c.variant === "error").length;

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return connections.filter((item) => {
      const matchesCategory = activeCategory === "All" || item.category === activeCategory;
      const matchesSearch = !q || item.name.toLowerCase().includes(q) || item.dbType?.toLowerCase().includes(q);
      return matchesCategory && matchesSearch;
    });
  }, [connections, activeCategory, search]);

  async function handleRetry(id) {
    await heartbeatConnection(id);
    revalidate();
  }

  return (
    <>
      <SectionTabs
        items={CONNECTIONS_SECTION_TABS}
        right={
          <span>
            {connections.length} connections{needsAttention ? ` · ${needsAttention} needs attention` : ""}
          </span>
        }
      />

      <div className="connections-page">
        <div className="connections-header">
          <div>
            <h1 className="connections-title">Connections</h1>
            <div className="connections-subtitle">
              {connections.length} connected
              {needsAttention ? ` · ${needsAttention} needs attention` : ""}
            </div>
          </div>
          <Button register="primary" onClick={() => setSheetOpen(true)}>
            <Plus size={13} aria-hidden="true" />
            Add connection
          </Button>
        </div>

        <CategoryToolbar
          categories={categories}
          active={activeCategory}
          onSelect={setActiveCategory}
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Search connections…"
        />

        <div className="connections-grid-wrap">
          <Panel flush>
            <Table>
              <thead>
                <tr>
                  <th>Connection</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th className="num">Schemas</th>
                  <th className="num">Tables</th>
                  <th></th>
                </tr>
              </thead>
              {loading ? (
                <TableEmpty colSpan={6}>Loading connections&hellip;</TableEmpty>
              ) : rows.length ? (
                <tbody>
                  {rows.map((conn) => {
                    const catalogEntry = CONNECTOR_CATALOG.find((c) => c.id === conn.dbType);
                    return (
                      <tr key={conn.id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                            <span className="conn-icon">{catalogEntry?.icon || String(conn.dbType || "").toUpperCase()}</span>
                            <div>
                              <div className="conn-title">{conn.name}</div>
                              <div className="conn-sub">{catalogEntry?.name || conn.dbType}</div>
                            </div>
                          </div>
                        </td>
                        <td>{conn.category}</td>
                        <td>
                          <StatusRow tone={conn.statusTone} label={conn.statusLabel} detail={conn.statusDetail} />
                        </td>
                        <td className="num mono">{conn.stats?.schemas ?? "—"}</td>
                        <td className="num mono">{conn.stats?.tables ?? "—"}</td>
                        <td>
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: "4px" }}>
                            {conn.variant === "error" ? (
                              <button
                                type="button"
                                className="btn btn-ghost btn-icon"
                                aria-label="Retry connection"
                                title="Retry connection"
                                onClick={() => handleRetry(conn.id)}
                              >
                                <RefreshCw size={14} aria-hidden="true" />
                              </button>
                            ) : null}
                            {conn.variant === "connected" || conn.variant === "warning" ? (
                              <button
                                type="button"
                                className="btn btn-ghost btn-icon"
                                aria-label="Ingestion settings"
                                title="Ingestion settings"
                                onClick={() => navigate(`/connections/${conn.id}/ingestion`)}
                              >
                                <SlidersHorizontal size={14} aria-hidden="true" />
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="btn btn-ghost btn-icon"
                              aria-label="Edit connection"
                              title="Edit connection"
                              onClick={() => setEditing(conn)}
                            >
                              <Pencil size={14} aria-hidden="true" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              ) : (
                <TableEmpty colSpan={6}>No connections match your filters.</TableEmpty>
              )}
            </Table>
          </Panel>
        </div>
      </div>

      <AddConnectionSheet isOpen={sheetOpen} onClose={() => setSheetOpen(false)} />
      <EditConnectionSheet isOpen={!!editing} connection={editing} onClose={() => setEditing(null)} onSaved={revalidate} />
    </>
  );
}
