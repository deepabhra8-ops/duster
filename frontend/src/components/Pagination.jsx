/**
 * Pagination.jsx - the footer bar under every paginated list.
 *
 * Was a bare row of « ‹ 1 2 3 › » buttons that rendered nothing at all on a
 * single page. That last part is the reason this grew: on one page the user was
 * told nothing - not how many rows there were, not that they were seeing all of
 * them, and with no way to ask for more per page. "Showing 1-8 of 8 jobs" is
 * worth a line on its own, so the bar now renders whenever it knows the total,
 * even when there is only one page of it.
 *
 * Every added prop is optional, and with none of them this behaves exactly as
 * before - a pager that hides itself below two pages. Rules.jsx and
 * JobsTable.jsx still call it that way; the jobs lists pass the rest.
 *
 * @param {number}   page         1-based current page.
 * @param {number}   totalPages   Total pages available.
 * @param {Function} onPage       Called with the page to move to.
 * @param {number}   [total]      Total rows across all pages. Enables the
 *                                "Showing X-Y of N" summary.
 * @param {number}   [pageSize]   Rows per page - needed to work out the range.
 * @param {Function} [onPageSize] Called with a new page size. Enables the
 *                                "Rows per page" select; omit it and the
 *                                choice is simply not offered.
 * @param {string}   [noun]       What a row is, for the summary ("jobs").
 */
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

export default function Pagination({
  page,
  totalPages,
  onPage,
  total,
  pageSize,
  onPageSize,
  noun = "rows",
}) {
  const knowsTotal = Number.isFinite(total) && Number.isFinite(pageSize);

  // Hide entirely only when there is nothing to say: one page AND no summary to
  // show. Previously this returned null on one page regardless.
  if ((!totalPages || totalPages <= 1) && !knowsTotal) return null;

  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  const nums = [];
  for (let p = start; p <= end; p++) nums.push(p);

  // Clamped against `total` so the last page reads "41-48 of 48" rather than
  // "41-50 of 48" when it is not full.
  const firstRow = knowsTotal && total > 0 ? (page - 1) * pageSize + 1 : 0;
  const lastRow = knowsTotal ? Math.min(page * pageSize, total) : 0;

  return (
    <div className="list-footer">
      {knowsTotal ? (
        <span className="list-footer-summary">
          {total === 0
            ? `No ${noun}`
            : `Showing ${firstRow}–${lastRow} of ${total} ${noun}`}
        </span>
      ) : (
        <span />
      )}

      <div className="list-footer-controls">
        {totalPages > 1 ? (
          <div className="pagination-bar">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => onPage(page - 1)}
              aria-label="Previous page"
            >
              &#8249;
            </button>
            {nums.map((p) => (
              <button
                key={p}
                type="button"
                className={p === page ? "active" : ""}
                aria-current={p === page ? "page" : undefined}
                onClick={() => onPage(p)}
              >
                {p}
              </button>
            ))}
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => onPage(page + 1)}
              aria-label="Next page"
            >
              &#8250;
            </button>
          </div>
        ) : null}

        {onPageSize ? (
          <label className="list-footer-size">
            Rows per page
            <select
              className="filter-select"
              value={pageSize}
              onChange={(e) => onPageSize(Number(e.target.value))}
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
    </div>
  );
}
