/**
 * ReportSheetGrid.jsx - one report sheet's data grid: #, Table, Column, CDE,
 * Rule ID, Rule Notes, Invalid Count, Total Count, Score, Score Bar.
 *
 * Renders exactly the rows it is handed - the caller does the filtering and the
 * paging, and passes `startIndex` so the "#" column keeps counting across
 * pages.
 *
 * Column set and Score colouring mirror the backend's real report sheets -
 * DimensionReport.DEFAULT_COLUMNS for the headers; the Score cell's
 * conditional colour is the same idea as DimensionWorkbookWriter's
 * per-cell fill in the real Excel sheet (GREEN_FILL/YELLOW_FILL/RED_FILL
 * there, a `.pill.sc-good/sc-warn/sc-bad` badge here - a plain `<span>`
 * rather than colouring the `<td>` itself, same as FindingsTable.jsx's
 * Score column, so `.tbl tr:hover td`'s background doesn't fight it) - same
 * good/warning/poor thresholds too (>=95% / >=80% / below,
 * DimensionScorer.GOOD_THRESHOLD/WARNING_THRESHOLD), via the
 * scoreClass()/scoreColorVar() helpers the rest of the app already uses for
 * RAG colouring, so the Score badge's colour and the Score Bar's fill
 * colour always agree. "Score Bar" itself is rendered as an actual
 * horizontal bar (ProgressBar.jsx) rather than the block-character bar
 * (`score_bar()`) the backend's own Excel sheet renders it as.
 */
import ProgressBar from "../ProgressBar.jsx";
import { fmtPct, scoreClass, scoreColorVar } from "../../utils/helpers.js";

const COLUMNS = [
  "#",
  "Table",
  "Column",
  "CDE",
  "Rule ID",
  "Rule Notes",
  "Invalid Count",
  "Total Count",
  "Score",
  "Score Bar",
];

const SKELETON_ROWS = 8;

/** Whether this row's check could not be performed.
 *
 * Both conditions matter: `status` is what the engine now sends, and the null
 * score covers a summary stored by an engine build that predates it. A row
 * with neither is a real result and renders its score normally.
 */
function isNotRun(row) {
  return row.status === "not_run" || row.score == null;
}

// Per-column placeholder widths, so the loading grid reads as tabular data
// rather than ten identical bars - narrow for counts, wide for Rule Notes.
const SKELETON_WIDTHS = ["24px", "70%", "70%", "18px", "44px", "88%", "50%", "50%", "48px", "100%"];

export default function ReportSheetGrid({ rows = [], loading = false, startIndex = 0 }) {
  if (!loading && rows.length === 0) {
    return <p className="empty-state">No rows for this sheet.</p>;
  }

  return (
    /* One scroll container, not two. The outer div duplicated .table-scroll's
       own overflowX, so a wide sheet produced a scrollbar on the wrapper box
       AND on the table - the box one being the wrong place for it. */
    <div className="table-scroll">
      <table className="tbl profile-map-table redesigned report-sheet-table" aria-busy={loading || undefined}>
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: SKELETON_ROWS }, (_, rowIndex) => (
                <tr key={`skeleton-${rowIndex}`} aria-hidden="true">
                  {SKELETON_WIDTHS.map((width, columnIndex) => (
                    <td key={columnIndex}>
                      {/* Staggered per row so the shimmer runs down the grid as a
                          wave instead of every row pulsing in lockstep. */}
                      <span
                        className="skeleton-cell"
                        style={{ width, animationDelay: `${rowIndex * 0.08}s` }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading && rows.map((row, i) => (
              <tr key={`${row.table}:${row.column}:${row.ruleId}:${i}`}>
                {/* Continues across pages: the caller passes the offset of the
                    first row on screen, so page 2 starts at 6 rather than at 1
                    again. */}
                <td>{startIndex + i + 1}</td>
                <td>{row.table}</td>
                <td>{row.column}</td>
                <td>{row.cde ? "✓" : ""}</td>
                <td>
                  <span className="pill pill-blue">{row.ruleId}</span>
                </td>
                <td>{row.ruleNotes}</td>
                <td>{row.invalidCount}</td>
                <td>{row.totalCount}</td>
                {/* A check that could not run has no score. Its underlying value
                    is a perfect 1.0 (an all-pass mask, because a rule that cannot
                    run cannot say which rows are bad), so rendering it as "100%"
                    told people a check had passed when it never executed. The
                    reason is in Rule Notes; the bar is omitted because there is
                    no measurement to draw. */}
                {isNotRun(row) ? (
                  <>
                    <td>
                      <span className="pill pill-gray" title={row.ruleNotes}>NOT RUN</span>
                    </td>
                    <td style={{ minWidth: "120px" }} />
                  </>
                ) : (
                  <>
                    <td>
                      <span className={`pill ${scoreClass(row.score)}`}>{fmtPct(row.score)}</span>
                    </td>
                    <td style={{ minWidth: "120px" }}>
                      <ProgressBar percent={Math.round(row.score * 1000) / 10} colorVar={scoreColorVar(row.score)} />
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
      </table>
    </div>
  );
}
