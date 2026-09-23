/**
 * JobDownloadCard.jsx - the side-rail download card for a job's generated
 * workbook: ProfileMapperJob.jsx's profile map, ValidatorJob.jsx's DQ report.
 *
 * Download-only by design. This used to be a two-box "Files" card, but the
 * Uploads box had nothing left to list (the configured-source-file and per-job
 * attachment endpoints were removed), so it rendered a permanently empty shell.
 *
 * The caller owns what the file is and how to fetch it - this only renders it,
 * and names the card via `title` (the Validator's results page calls it
 * "Download Report").
 */
export default function JobDownloadCard({ showDownload, downloadFilename, onDownload, isDownloading, loading = false, title = "Download" }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>

      {loading ? (
        // Same shape as the real card (file row + full-width button), so the
        // side rail is already the right size before the job resolves.
        <div className="job-download" aria-hidden="true">
          <div className="job-download-file">
            <span className="skeleton job-download-icon" />
            <span className="skeleton skeleton-text" style={{ flex: 1, margin: 0 }} />
          </div>
          <span className="skeleton job-download-btn-skeleton" />
        </div>
      ) : (
        <div className="job-download">
          <div className="job-download-file">
            <img src="/icons/xls.svg" alt="" className="job-download-icon" aria-hidden="true" style={!showDownload ? { filter: 'grayscale(100%)', opacity: 0.5 } : {}} />
            <span className="job-download-name" title={downloadFilename} style={!showDownload ? { color: 'var(--text-light)' } : {}}>
              {downloadFilename}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onDownload}
            disabled={!showDownload || isDownloading}
            style={isDownloading ? { filter: 'grayscale(100%)', opacity: 0.7, cursor: 'not-allowed' } : {}}
          >
            {isDownloading ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="metadata-spinner" aria-hidden="true" style={{ width: '14px', height: '14px' }} />
                Downloading...
              </span>
            ) : (
              'Download'
            )}
          </button>
        </div>
      )}
    </div>
  );
}
