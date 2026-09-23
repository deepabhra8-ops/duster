import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import Pagination from "../Pagination.jsx";
import Tabs from "../Tabs.jsx";
import ReportSheetGrid from "./ReportSheetGrid.jsx";

export const NOT_RUN_TAB = "Not Run";

const ALL_TABLES = "All Tables";
const DEFAULT_PAGE_SIZE = 10;

export function isNotRunRow(row) {
  return row.status === "not_run" || row.score == null;
}

function matches(row, needle) {
  return Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(needle));
}

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

  useEffect(() => {
    setPage(1);
  }, [activeSheet, activeTable, query, pageSize]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const pageRows = useMemo(
    () => rows.slice((page - 1) * pageSize, page * pageSize),
    [rows, page, pageSize]
  );

  const firstIndex = (page - 1) * pageSize;

  return (
    <>
      <div className="results-toolbar">
        <div className="report-toolbar-actions">
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
