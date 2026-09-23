/**
 * Connections.jsx - saved database connections manager.
 *
 * Replaces the old Configure page for the "Configure" nav item (see
 * docs/ux-plan.md §3). Two-stacked-card layout (toolbar above, table
 * below), same structure as Profile Mapper (§5). Wired to the real
 * backend - GET /api/connections now returns description/port too (a
 * schema migration added those columns; port is derived server-side from
 * connectionDetails.port where the db type has one, else NULL, shown here
 * as "-"). Create and the row's Edit button both open the same real
 * ConnectionWizardModal (genuinely saves via the API - POST for Create,
 * PATCH for Edit, see that modal's own header comment for how it prefills
 * from the row + a reveal call); Delete calls the real DELETE endpoint.
 * Edit was a dead button before - no onClick at all.
 */
import { useCallback, useEffect, useState } from "react";
import { Eye, Trash2 } from "lucide-react";
import RefreshButton from "../components/RefreshButton.jsx";
import Pagination from "../components/Pagination.jsx";
import ConnectionWizardModal from "../components/configure/ConnectionWizardModal.jsx";
import ViewConnectionModal from "../components/configure/ViewConnectionModal.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { deleteConnection, listConnections } from "../api/api.js";
import { CONNECTIONS_PAGE_SIZE, DEBOUNCE_DELAY, PAGE_META } from "../constants/appConfig.js";
import { IconError } from "../components/Icons.jsx";
import { DATABASE_TYPE_OPTIONS } from "../constants/sourceTypes.js";
import { useAuth } from "../hooks/useAuth.js";
import { useCachedResource } from "../hooks/useCachedResource.js";
import { buildKey, invalidate, resourcePrefix } from "../utils/pageCache.js";
import { useToast } from "../hooks/useToast.js";

const DB_TYPE_LABELS = Object.fromEntries(DATABASE_TYPE_OPTIONS.map((o) => [o.value, o.label]));

export default function Connections() {
  const meta = PAGE_META.configure;
  const { showToast } = useToast();
  const { username } = useAuth();

  const [wizardOpen, setWizardOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState(null);
  const [viewingConnection, setViewingConnection] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  /* Phase 5: ConfirmDialog state instead of window.confirm */
  const [confirmState, setConfirmState] = useState(null);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState(CONNECTIONS_PAGE_SIZE);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sortOrder, setSortOrder] = useState("desc");

  /* Debounce search -> reset to page 1, same as useJobList. */
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, DEBOUNCE_DELAY);
    return () => clearTimeout(t);
  }, [searchInput]);

  function setPageSize(size) {
    setPageSizeState(size);
    setPage(1);
  }

  function changeTypeFilter(value) {
    setTypeFilter(value);
    setPage(1);
  }

  function changeSortOrder(value) {
    setSortOrder(value);
    setPage(1);
  }

  // The connections list is SHARED across users (list_page() has no owner
  // filter), so it is cached under the "shared" scope rather than per user.
  // Paginated, searched and sorted server-side now (see api.js's
  // listConnections/GET /api/connections), so every input that changes the
  // response is folded into the key - same shape useJobList uses for jobs.
  const cacheKey = buildKey("shared", "connections", {
    page,
    pageSize,
    search,
    dbType: typeFilter,
    sortOrder,
  });

  const fetcher = useCallback(
    () => listConnections({ page, pageSize, search, dbType: typeFilter, sortOrder }),
    [page, pageSize, search, typeFilter, sortOrder]
  );

  const select = useCallback(
    (data) => ({
      connections: data?.data || [],
      total: data?.total || 0,
      totalPages: data?.totalPages || 1,
    }),
    []
  );

  const {
    data,
    error,
    loading,
    refreshing,
    lastUpdated,
    refresh,
  } = useCachedResource({ key: cacheKey, fetcher, select });

  const connections = data?.connections || [];
  const total = data?.total || 0;
  const totalPages = data?.totalPages || 1;

  /** A connection change also moves the dashboard's Connections tile. */
  function invalidateDashboard() {
    invalidate(resourcePrefix(username, "dashboard"));
  }

  /** Every cached page of connections is stale after a mutation - offset
      pagination means a create/delete shifts later pages, not just the one
      on screen. Mirrors useJobList's invalidateAndReload. */
  function invalidateAndReload() {
    invalidate(resourcePrefix("shared", "connections"));
    invalidateDashboard();
    refresh();
  }

  function openCreate() {
    setEditingConnection(null);
    setWizardOpen(true);
  }

  function openEdit(connection) {
    setEditingConnection(connection);
    setWizardOpen(true);
  }

  function closeWizard() {
    setWizardOpen(false);
    setEditingConnection(null);
  }

  function openView(connection) {
    setViewingConnection(connection);
  }

  function closeView() {
    setViewingConnection(null);
  }

  /** Create jumps back to page 1 (newest-first is the default sort, so that's
      where a new connection lands); Edit and Delete stay on the current page -
      both just invalidate every cached page and refetch, same as useJobList. */
  function handleSaved() {
    const wasEditing = Boolean(editingConnection);
    closeWizard();
    if (!wasEditing) setPage(1);
    invalidateAndReload();
  }

  async function handleDelete(id, name) {
    setConfirmState({ id, name });
  }

  async function confirmDelete() {
    if (!confirmState) return;
    const { id, name } = confirmState;
    setConfirmState(null);
    setDeletingId(id);
    const { ok, error: err } = await deleteConnection(id);
    setDeletingId(null);
    if (!ok) {
      showToast({ type: "error", title: "Couldn't delete connection", message: err || "Failed to delete connection." });
      return;
    }
    invalidateAndReload();
    showToast({ type: "success", title: "Connection deleted", message: `"${name}" was deleted.` });
  }

  return (
    <section>
      <header className="page-header">
        <h2>{meta.title}</h2>
        <p>{meta.subtitle}</p>
      </header>

      {/* Top section: actions + filters. */}
      <div className="card page-fill">
        <div className="uploads-toolbar row-between">
          <div className="row" style={{ gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
            <input
              type="text"
              className="search-input"
              placeholder="Search by Connection Name…"
              autoComplete="off"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            <div className="filter-group">
              <select className="filter-select" value={typeFilter} onChange={(e) => changeTypeFilter(e.target.value)}>
                <option value="">All Database Types</option>
                {DATABASE_TYPE_OPTIONS.filter((o) => o.value).map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="row" style={{ gap: "8px", alignItems: "center" }}>
            <RefreshButton onRefresh={refresh} refreshing={refreshing} lastUpdated={lastUpdated} />
            <button
              type="button"
              className="btn btn-primary"
              onClick={openCreate}
            >
              Create
            </button>
          </div>
        </div>

        {/* One card holds the toolbar and the table, matching ProfileMapper -
            a second card put a visible gap between a filter and the rows it
            filters, which read as two unrelated panels. The "Saved Connections"
            card title went with it: the page header already says Connections,
            and ProfileMapper's equivalent table carries no title either. */}
        {loading ? (
          <div aria-busy="true" aria-label="Loading connections…">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="skeleton skeleton-row" />
            ))}
          </div>
        ) : error ? (
          <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> {error}</div>
        ) : total === 0 && !search && !typeFilter ? (
          <div className="empty-state">
            <span className="empty-state-icon">🔌</span>
            <span className="empty-state-text">No saved connections yet</span>
            <span className="empty-state-sub">Add a database connection to power your pipelines.</span>
            <div className="row" style={{ gap: "8px", alignItems: "center" }}>
            <button type="button" className="btn btn-primary" onClick={openCreate}>Create Connection</button>
            </div>
          </div>
        ) : connections.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="32" height="32">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </span>
            <span className="empty-state-text">No connections match your search or filter</span>
          </div>
        ) : (
          <div className="tbl-scroll">
            <table className="tbl tbl-sticky profile-map-table redesigned jobs-list-table" aria-label="Saved connections">
              <thead>
                <tr>
                  <th>ID</th>
                  <th style={{ paddingLeft: "32px" }}>Name</th>
                  <th style={{ paddingLeft: "32px" }}>Description</th>
                  <th style={{ paddingLeft: "32px" }}>DB Type</th>
                  <th style={{ paddingLeft: "32px" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr key={c.id}>
                    <td data-label="ID">
                      <span className="mono">{c.id}</span>
                    </td>
                    <td className="job-name-cell" style={{ paddingLeft: "32px" }} data-label="Name" title={c.name || ""}>{c.name}</td>
                    <td className="job-desc-cell hint" style={{ paddingLeft: "32px" }} data-label="Description" title={c.description || ""}>{c.description || "—"}</td>
                    <td style={{ paddingLeft: "32px" }} data-label="DB Type">
                      <span className="pill pill-blue">{DB_TYPE_LABELS[c.db_type] || c.db_type}</span>
                    </td>
                    <td style={{ paddingLeft: "32px" }} data-label="Actions">
                      <div className="file-action-btns">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-icon-only"
                          onClick={() => openView(c)}
                          aria-label={`View connection ${c.name}`}
                          title="View"
                        >
                          <Eye size={16} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-icon-only"
                          onClick={() => openEdit(c)}
                          aria-label={`Edit connection ${c.name}`}
                          title="Edit"
                        >
                          <span className="btn-icon" style={{ "--icon-src": "url(/icons/edit.svg)" }} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm btn-icon-only"
                          disabled={deletingId === c.id}
                          onClick={() => handleDelete(c.id, c.name)}
                          aria-label={`Delete connection ${c.name}`}
                          title="Delete"
                        >
                          {/* The same lucide Trash2 the Profile Mapper and
                              Validator tables use. This row had a mask-based
                              /icons/delete.svg instead - a different bin at a
                              different weight, in the one place a user is most
                              likely to compare the two, since all three tables
                              share a layout. */}
                          <Trash2 size={16} aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Hidden during loading/error - total/totalPages are meaningless
            (still 0/1 from before the first response) until a page actually
            lands. */}
        {!loading && !error ? (
          <Pagination
            page={page}
            totalPages={totalPages}
            onPage={setPage}
            total={total}
            pageSize={pageSize}
            onPageSize={setPageSize}
            noun="connections"
          />
        ) : null}
      </div>

      <ConnectionWizardModal
        open={wizardOpen}
        onClose={closeWizard}
        onSaved={handleSaved}
        editingConnection={editingConnection}
      />

      <ViewConnectionModal
        open={Boolean(viewingConnection)}
        onClose={closeView}
        connection={viewingConnection}
        onEdit={openEdit}
        dbTypeLabel={viewingConnection ? DB_TYPE_LABELS[viewingConnection.db_type] || viewingConnection.db_type : ""}
      />

      {/* Phase 5: ConfirmDialog replaces window.confirm for destructive delete */}
      <ConfirmDialog
        open={Boolean(confirmState)}
        title="Delete Connection"
        subject={confirmState?.name}
        message="This will permanently remove the connection and cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setConfirmState(null)}
      />
    </section>
  );
}
