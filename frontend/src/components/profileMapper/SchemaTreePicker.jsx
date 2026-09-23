import { useEffect, useMemo, useState } from "react";

import { Folder, FolderOpen, Table2, Columns3, Trash2 } from "lucide-react";

import SearchableSelect from "../SearchableSelect.jsx";
import { useCatalog } from "../../hooks/useCatalog.js";

export const MAX_TABLES = 5;

export const EMPTY_ROW = { schema: "", table: "", column: "", locked: false };

const toOptions = (names) => names.map((name) => ({ value: name, label: name }));

const keyOf = (schema, table) => `${schema}.${table}`;

const TABLE_SKELETON_WIDTHS = ["72%", "54%", "83%", "61%", "45%"];

export default function SchemaTreePicker({
  rows,
  onChange,
  connectionId,
  schemas = [],
  columnLabel = "Column",
}) {
  const { loadTables, loadColumns, tablesFor, columnsFor } = useCatalog(connectionId);
  const [expanded, setExpanded] = useState(
    () => new Set(rows.filter((row) => row.schema && row.table).map((row) => row.schema))
  );
  const [search, setSearch] = useState("");

  const selected = useMemo(
    () => rows.filter((row) => row.schema && row.table),
    [rows]
  );
  const selectedKeys = useMemo(
    () => new Set(selected.map((row) => keyOf(row.schema, row.table))),
    [selected]
  );
  const atLimit = selected.length >= MAX_TABLES;

  useEffect(() => {
    for (const schema of new Set(selected.map((row) => row.schema))) {
      loadTables(schema);
    }
    for (const row of selected) {
      loadColumns(row.schema, row.table);
    }
  }, [selected, loadTables, loadColumns]);

  const sortedSchemas = useMemo(() => [...schemas].sort(), [schemas]);

  function toggleSchema(schema) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(schema)) {
        next.delete(schema);
      } else {
        next.add(schema);
        loadTables(schema);
      }
      return next;
    });
  }

  function toggleTable(schema, table) {
    const key = keyOf(schema, table);

    if (selectedKeys.has(key)) {
      onChange(selected.filter((row) => keyOf(row.schema, row.table) !== key));
      return;
    }
    if (atLimit) return;

    loadColumns(schema, table);
    onChange([...selected, { schema, table, column: "", locked: true }]);
  }

  function setColumn(key, value) {
    onChange(
      selected.map((row) =>
        keyOf(row.schema, row.table) === key ? { ...row, column: value } : row
      )
    );
  }

  const query = search.trim().toLowerCase();

  function visibleTables(schema) {
    const items = tablesFor(schema).items;
    if (!query) return items;
    if (schema.toLowerCase().includes(query)) return items;
    return items.filter((t) => t.toLowerCase().includes(query));
  }

  function schemaMatches(schema) {
    if (!query) return true;
    if (schema.toLowerCase().includes(query)) return true;
    return expanded.has(schema) && visibleTables(schema).length > 0;
  }

  const shownSchemas = sortedSchemas.filter(schemaMatches);

  if (sortedSchemas.length === 0) {
    return (
      <div className="stc">
        <div className="card-title stc-title">Select Tables &amp; Columns</div>
        <p className="empty-state">No schemas available for this connection yet.</p>
      </div>
    );
  }

  return (
    <div className="stc">
      <div className="stc-title-row">
        <div className="card-title stc-title">Select Tables &amp; Columns</div>
        <span className={`stp-count${atLimit ? " is-full" : ""}`}>
          {selected.length} of {MAX_TABLES} tables
        </span>
      </div>

      <input
        type="text"
        className="stp-search"
        placeholder="Filter schemas and tables…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        aria-label="Filter schemas and tables"
      />

      <div className="stp-panes">
        <div className="stp-tree" role="tree" aria-label="Schemas and tables">
          {shownSchemas.length === 0 ? (
            <p className="empty-state">No schema or table matches that filter.</p>
          ) : (
            shownSchemas.map((schema) => {
              const isOpen = expanded.has(schema);
              const catalog = tablesFor(schema);
              const tables = visibleTables(schema);

              return (
                <div className="stp-node" key={schema}>
                  <button
                    type="button"
                    className="stp-schema"
                    onClick={() => toggleSchema(schema)}
                    aria-expanded={isOpen}
                  >
                    <span className={`stp-caret${isOpen ? " is-open" : ""}`} aria-hidden="true">
                      &#9654;
                    </span>
                    {isOpen ? (
                      <FolderOpen size={14} className="stp-icon stp-icon-schema" aria-hidden="true" />
                    ) : (
                      <Folder size={14} className="stp-icon stp-icon-schema" aria-hidden="true" />
                    )}
                    <span className="stp-label">{schema}</span>
                  </button>

                  {isOpen ? (
                    <div className="stp-children" role="group">
                      {!catalog.loaded && !catalog.error ? (
                        <div className="stp-skeletons" aria-label="Loading tables">
                          {TABLE_SKELETON_WIDTHS.map((width, i) => (
                            <div className="stp-skeleton-row" key={i}>
                              <span
                                className="skeleton-cell"
                                style={{ width, animationDelay: `${i * 0.08}s` }}
                              />
                            </div>
                          ))}
                        </div>
                      ) : catalog.error ? (
                        <p className="stp-note stp-error">{catalog.error}</p>
                      ) : tables.length === 0 ? (
                        <p className="stp-note">
                          {query ? "No matching tables." : "No tables in this schema."}
                        </p>
                      ) : (
                        tables.map((table) => {
                          const key = keyOf(schema, table);
                          const isSelected = selectedKeys.has(key);
                          const blocked = !isSelected && atLimit;

                          return (
                            <label
                              key={table}
                              className={`stp-table${isSelected ? " is-selected" : ""}${blocked ? " is-blocked" : ""}`}
                              title={blocked ? `At most ${MAX_TABLES} tables per job` : table}
                            >
                              <input
                                type="checkbox"
                                checked={isSelected}
                                disabled={blocked}
                                onChange={() => toggleTable(schema, table)}
                              />
                              <Table2 size={14} className="stp-icon stp-icon-table" aria-hidden="true" />
                              <span className="stp-label">{table}</span>
                            </label>
                          );
                        })
                      )}
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>

        <div className="stp-selected">
          {selected.length === 0 ? (
            <p className="empty-state stp-empty">
              Expand a schema and tick up to {MAX_TABLES} tables. Each one needs a{" "}
              {columnLabel.toLowerCase()}.
            </p>
          ) : (
            selected.map((row) => {
              const key = keyOf(row.schema, row.table);
              const columns = columnsFor(row.schema, row.table);

              return (
                <div className={`stp-chosen${row.column ? "" : " needs-column"}`} key={key}>
                  <div className="stp-chosen-head">
                    <span className="stp-chosen-name" title={key}>
                      <span className="stp-chosen-schema">{row.schema}.</span>
                      {row.table}
                    </span>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm btn-icon-only"
                      onClick={() => toggleTable(row.schema, row.table)}
                      aria-label={`Remove ${key}`}
                      title="Remove"
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </button>
                  </div>

                  <label className="stp-chosen-label">
                    <Columns3 size={12} className="stp-icon stp-icon-column" aria-hidden="true" />
                    {columnLabel}
                  </label>
                  <SearchableSelect
                    value={row.column}
                    options={toOptions(columns.items)}
                    onChange={(v) => setColumn(key, v)}
                    placeholder={`Search ${columnLabel.toLowerCase()}…`}
                    emptyLabel="No columns in this table"
                    loading={columns.loading || (!columns.loaded && !columns.error)}
                  />
                  {columns.error ? (
                    <p className="stc-row-error">{columns.error}</p>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
