/**
 * ReportResultsTabs.jsx - tabbed view over every report sheet the DQ
 * Validator generates, off the real job's `summary.sheets`
 * (engine/reporting/validation_summary.py::build_summary on the backend, built
 * by the Glue run and stored in `validation_results` - see ValidatorJob.jsx,
 * which fetches the job and passes its `sheets` object down here as a prop).
 *
 * Everything on this toolbar filters the rows ALREADY IN MEMORY. `summary` is
 * fetched once with the job; switching tab, picking a table, typing a search or
 * turning a page never issues a request, so every one of them lands on the next
 * frame. That is a property worth stating because the controls look like the
 * server-side ones on the jobs list, which do refetch.
 *
 * Three things the strip carries beyond the sheet names:
 *
 *   - Counts, e.g. "Completeness (6)". A tab whose sheet is empty is worth
 *     knowing about BEFORE clicking it.
 *
 *   - A "Not Run" tab. Checks that could not execute were scattered through
 *     All Findings as NOT RUN rows, which is exactly where you cannot find them
 *     when the banner above says 30 of them exist. It is a view over All
 *     Findings rather than a sheet of its own - the backend sends no such
 *     sheet, and deriving it costs one filter.
 *
 *   - A Table filter. Previously this was a second row of tabs, one per table,
 *     which does not survive a connection with more than a handful of them.
 *
 * "Failed Rows" is excluded: its rows are per failing record rather than per
 * rule, so it does not fit this grid's columns.
 */
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import Pagination from "../Pagination.jsx";
import Tabs from "../Tabs.jsx";
import ReportSheetGrid from "./ReportSheetGrid.jsx";

/** The derived tab id - not a key in `sheets`. See the header comment. */
export const NOT_RUN_TAB = "Not Run";

const ALL_TABLES = "All Tables";
const DEFAULT_PAGE_SIZE = 10;

/** A check that could not be performed. `status` is what the engine sends; the
 *  null score covers a summary stored by a build that predates it. */
export function isNotRunRow(row) {
  return row.status === "not_run" || row.score == null;
}

/** Case-insensitive match against every value in the row. */
function matches(row, needle) {
  return Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(needle));
}

/** Placeholder tab strip. The outer span keeps .tab's own padding and border,
 *  so the strip is exactly as tall as the real Tabs row it stands in for and
 *  the grid below does not move when the tabs resolve; only the label is
 *  swapped for a shimmering bar. */
function SkeletonTabs({ widths }) {
  return (
    <div className="tabs" aria-hidden="true">
      {widths.map((width, index) => (
        <span key={index} className="tab tab-skeleton">
          <span
            className="tab-skeleton-bar"
            style={{ width, animationDelay: `${index * 0.1}s` }}
          />
        </span>
      ))}
    </div>
  );
}

export default function ReportResultsTabs({
  tables = [],
  sheets = {},
  loading = false,
  /** Lets the page's "View Not Run" banner button drive the tab strip. */
  activeSheet: controlledSheet,
  onSheetChange,
}) {
  const [uncontrolledSheet, setUncontrolledSheet] = useState("All Findings");
  const activeSheet = controlledSheet ?? uncontrolledSheet;
  const setActiveSheet = onSheetChange ?? setUncontrolledSheet;

  const [activeTable, setActiveTable] = useState(ALL_TABLES);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const sheetNames = useMemo(
    () => Object.keys(sheets).filter((name) => name !== "Failed Rows"),
    [sheets]
  );

  const allFindings = useMemo(() => sheets["All Findings"] || [], [sheets]);
  const notRunRows = useMemo(() => allFindings.filter(isNotRunRow), [allFindings]);

  useEffect(() => {
    if (sheetNames.length > 0 && activeSheet !== NOT_RUN_TAB && !sheetNames.includes(activeSheet)) {
      setActiveSheet(sheetNames.includes("All Findings") ? "All Findings" : sheetNames[0]);
    }
  }, [sheetNames, activeSheet, setActiveSheet]);

  const sheetTabs = [
    ...sheetNames.map((name) => ({
      id: name,
      label: `${name} (${(sheets[name] || []).length})`,
    })),
    ...(notRunRows.length
      ? [{ id: NOT_RUN_TAB, label: `${NOT_RUN_TAB} (${notRunRows.length})` }]
      : []),
  ];

  const rows = useMemo(() => {
    let all = activeSheet === NOT_RUN_TAB ? notRunRows : sheets[activeSheet] || [];

    if (activeTable !== ALL_TABLES) {
      all = all.filter((row) => row.table === activeTable);
    }

    const needle = query.trim().toLowerCase();
    return needle ? all.filter((row) => matches(row, needle)) : all;
  }, [sheets, activeSheet, notRunRows, activeTable, query]);

  /* Any change to what is being filtered invalidates the page number - page 3
     of the old result set is usually past the end of the new one, which would
     render an empty grid over a non-empty result. */
  useEffect(() => {
    setPage(1);
  }, [activeSheet, activeTable, query, pageSize]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageRows = useMemo(
    () => rows.slice((page - 1) * pageSize, page * pageSize),
    [rows, page, pageSize]
  );

  /* The grid numbers its rows from 1; on page 2 that has to continue from where
     page 1 stopped rather than restarting. */
  const firstIndex = (page - 1) * pageSize;

  return (
    <>
      {/* Above the tab strip, not beside it. These two narrow the rows in EVERY
          tab, while a tab chooses which of those rows you are looking at - so
          they sit outside the strip rather than reading as another control
          belonging to the active tab. It also stops the strip and the toolbar
          fighting for one line once the tab labels carry their counts. */}
      <div className="results-toolbar">
        <div className="report-toolbar-actions">
          {/* Every table this run touched. A plain <select>: the list is short,
              it needs no search of its own, and it filters rows already held in
              memory - the change is visible on the next frame.

              Shown for a single-table run too. Hiding it below two tables made
              the control appear and disappear between jobs, so on a one-table
              run there was no sign the results were scoped to a table at all -
              and nothing naming which one. With one table it reads as a label
              that happens to be changeable. */}
          {tables.length > 0 ? (
            <select
              className="filter-select"
              value={activeTable}
              onChange={(e) => setActiveTable(e.target.value)}
              disabled={loading}
              aria-label="Filter by table"
            >
              <option value={ALL_TABLES}>All Tables</option>
              {tables.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          ) : null}

          <label className="results-search">
            <Search size={15} className="results-search-icon" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search tables, columns, rule IDs or notes…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
            />
          </label>
        </div>
      </div>

      <div className="report-tabs-row">
        {loading ? (
          <SkeletonTabs widths={["92px", "112px", "104px", "98px"]} />
        ) : (
          <Tabs tabs={sheetTabs} active={activeSheet} onChange={setActiveSheet} />
        )}
      </div>

      <div className="results-grid-wrap">
        <ReportSheetGrid rows={pageRows} loading={loading} startIndex={firstIndex} />
      </div>

      {!loading ? (
        <Pagination
          page={page}
          totalPages={totalPages}
          onPage={setPage}
          total={rows.length}
          pageSize={pageSize}
          onPageSize={setPageSize}
          noun="findings"
        />
      ) : null}
    </>
  );
}
