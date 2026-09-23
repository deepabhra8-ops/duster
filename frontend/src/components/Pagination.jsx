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

  if ((!totalPages || totalPages <= 1) && !knowsTotal) return null;

  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  const nums = [];
  for (let p = start; p <= end; p++) nums.push(p);

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
