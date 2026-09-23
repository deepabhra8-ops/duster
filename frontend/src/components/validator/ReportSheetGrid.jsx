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

function isNotRun(row) {
  return row.status === "not_run" || row.score == null;
}

const SKELETON_WIDTHS = ["24px", "70%", "70%", "18px", "44px", "88%", "50%", "50%", "48px", "100%"];

export default function ReportSheetGrid({ rows = [], loading = false, startIndex = 0 }) {
  if (!loading && rows.length === 0) {
    return <p className="empty-state">No rows for this sheet.</p>;
  }

  return (
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
