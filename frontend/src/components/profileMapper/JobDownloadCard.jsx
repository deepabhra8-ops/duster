export default function JobDownloadCard({ showDownload, downloadFilename, onDownload, isDownloading, loading = false, title = "Download" }) {
  return (
    <div className="card">
      <div className="card-title">{title}</div>

      {loading ? (
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
