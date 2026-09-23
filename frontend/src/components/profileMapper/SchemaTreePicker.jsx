/**
 * SchemaTreePicker.jsx - a database-browser tree for choosing the tables a job
 * runs against, and the key column for each.
 *
 * Replaces SchemaTableColumnRows.jsx's row-of-dropdowns. That design asked the
 * user to re-pick the schema for every table, gave no sense of what a
 * connection actually contains, and put the table list behind a dropdown that
 * opened as a narrow scrolling strip - unreadable against real names like
 * "AccountContactRelation". Picking five tables meant fifteen dropdown
 * interactions across five near-identical rows.
 *
 * The shape here is the one every database tool uses, because browsing is the
 * task: schemas expand to reveal their tables, tables are ticked, and the
 * ticked ones gather in a panel beside the tree where each gets its key column.
 * Nothing is fetched until a schema is expanded, and useCatalog caches per
 * connection, so re-expanding costs nothing.
 *
 * It emits exactly the row shape the old component did -
 * {schema, table, column, locked} - so both New Job modals and rowsToTables()
 * are untouched. `locked: true` on every emitted row because in this model a
 * row exists only where the user deliberately ticked a table, which is the same
 * assertion the old lock toggle was making: this row is a finished, intentional
 * choice. The modals' "at least one locked row" guard therefore still holds.
 */
import { useEffect, useMemo, useState } from "react";

import { Folder, FolderOpen, Table2, Columns3, Trash2 } from "lucide-react";

import SearchableSelect from "../SearchableSelect.jsx";
import { useCatalog } from "../../hooks/useCatalog.js";

/** A job may run against at most this many tables. The engine profiles each
 *  table inside one Glue run, so the ceiling is about run time and cost rather
 *  than anything structural. */
export const MAX_TABLES = 5;

export const EMPTY_ROW = { schema: "", table: "", column: "", locked: false };

const toOptions = (names) => names.map((name) => ({ value: name, label: name }));

const keyOf = (schema, table) => `${schema}.${table}`;

/* Placeholder rows while a schema's tables are in flight. Skeletons rather than
   a single spinner because they say how much is coming and where it will land,
   so the list does not jump when it arrives. The widths vary so the block reads
   as a list of names rather than a progress bar. */
const TABLE_SKELETON_WIDTHS = ["72%", "54%", "83%", "61%", "45%"];

export default function SchemaTreePicker({
  rows,
  onChange,
  connectionId,
  schemas = [],
  columnLabel = "Column",
}) {
  const { loadTables, loadColumns, tablesFor, columnsFor } = useCatalog(connectionId);
  /* Seeded from the incoming rows rather than empty. This component is mounted
     conditionally by the New Job wizards, so stepping Back and forward again
     destroys it; the parent still holds the selections, and re-opening onto a
     fully collapsed tree with the selections sitting in the side panel reads as
     if the tree had lost them. */
  const [expanded, setExpanded] = useState(
    () => new Set(rows.filter((row) => row.schema && row.table).map((row) => row.schema))
  );
  const [search, setSearch] = useState("");

  /* Rows arriving from the parent can be placeholders (a fresh modal seeds one
     blank row) - only the complete ones are real selections. */
  const selected = useMemo(
    () => rows.filter((row) => row.schema && row.table),
    [rows]
  );
  const selectedKeys = useMemo(
    () => new Set(selected.map((row) => keyOf(row.schema, row.table))),
    [selected]
  );
  const atLimit = selected.length >= MAX_TABLES;

  /* Re-request the catalog behind rows that are already selected.
   *
   * useCatalog holds its cache in useState, so it lives and dies with THIS
   * component. Columns were only ever fetched from toggleTable - the moment the
   * user ticked a table - which is fine for a picker that mounts once. These
   * wizards unmount it on Back and mount a fresh one on Next, and the parent
   * keeps the rows: the selections came back, their catalog did not, and
   * nothing asked for it again. columnsFor() then reported `loaded: false` with
   * no error, which is exactly the state the Column select renders as
   * "Loading…" - so the dropdown sat there spinning forever and the primary key
   * the user had already chosen never reappeared, because its option list was
   * empty.
   *
   * Both loaders no-op on anything already cached and fetchKey dedupes what is
   * in flight, so running this on every change costs nothing after the first
   * pass. */
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
        // Fetched on expand, not up front: a connection can carry dozens of
        // schemas and the user opens one or two.
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

  /* Search filters table names within the schemas already expanded, and matches
     schema names too - typing a schema name is the fastest way to find it in a
     long list. */
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
    // A schema whose tables match stays visible even if its own name does not,
    // but only once expanded - its table list is not loaded before that.
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
                    {/* Open/closed folder, the convention every database
                        browser uses for a schema node. */}
                    {isOpen ? (
                      <FolderOpen size={14} className="stp-icon stp-icon-schema" aria-hidden="true" />
                    ) : (
                      <Folder size={14} className="stp-icon stp-icon-schema" aria-hidden="true" />
                    )}
                    <span className="stp-label">{schema}</span>
                  </button>

                  {isOpen ? (
                    <div className="stp-children" role="group">
                      {/* `loaded` is checked, not just `loading`: a freshly
                          expanded schema has neither yet, and treating that as
                          "loaded and empty" is what made the tree claim "No
                          tables in this schema" before it had asked. */}
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
                          // At the limit the unticked tables go disabled rather
                          // than silently doing nothing when clicked.
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
                      {/* Same Trash2 as every other delete in the app. */}
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
                    /* Same rule as the tables above: until the fetch has
                       actually landed this is loading, not empty. */
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
