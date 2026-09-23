/**
 * LovUploadPanel.jsx - LOV (List of Values) upload panel.
 *
 * A LOV belongs to the job it was created with, not to the upload area. The
 * panel therefore has two shapes, chosen by whether `onChange` is passed:
 *
 *   - Job mode (`onChange` given, e.g. NewValidatorJobModal): the job's single
 *     LOV file. It starts empty for every new job - LOVs uploaded for earlier
 *     jobs are deliberately not offered, since validating against someone
 *     else's reference list is worse than not validating at all. Uploading a
 *     second file replaces the first.
 *   - Reference mode (no `onChange`, e.g. the Rules page): format help and the
 *     sample download only, with no file list, because there is no job here for
 *     a file to belong to.
 *
 * A LOV file is *wide*: every column is an independent list named by its
 * header, so the one file a job carries can cover every DQ8-checked column
 * across as many tables as it likes.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download,
  FileText,
  Loader2,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { getLov, sampleLovUrl, uploadFile } from "../api/api.js";
import { useToast } from "../hooks/useToast.js";

/**
 * @param {object} props
 * @param {string|null}  [props.value]      - Stored filename of the job's LOV
 * @param {Function}     [props.onChange]   - (filename|null) => void; enables job mode
 * @param {boolean}      [props.readOnly=false] - Hides upload/remove controls
 * @param {boolean}      [props.compact=false]  - More compact layout
 * @param {string}       [props.className=""]   - Additional CSS classes
 */
export default function LovUploadPanel({
  value = null,
  onChange = null,
  readOnly = false,
  compact = false,
  className = "",
}) {
  const { showToast } = useToast();
  const fileInputRef = useRef(null);

  const jobMode = typeof onChange === "function" || Boolean(value);

  const [entry, setEntry] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  /* ── Describe the job's file ───────────────────────────────── */
  useEffect(() => {
    let cancelled = false;

    if (!value) {
      setEntry(null);
      return undefined;
    }

    setLoading(true);
    getLov(value)
      .then((res) => {
        if (cancelled) return;
        setEntry(res.ok ? res.data?.data || null : null);
      })
      .catch(() => {
        /* the row falls back to the filename alone */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [value]);

  /* ── Upload ────────────────────────────────────────────────── */
  const handleUpload = useCallback(
    async (selected) => {
      if (!selected || selected.length === 0) return;

      // One LOV per job. A multi-file drop is refused outright rather than
      // silently keeping whichever happened to land last.
      if (selected.length > 1) {
        showToast({
          type: "error",
          title: "One file only",
          message:
            "A job validates against a single LOV file. Put every list in one CSV, one column per LOV.",
        });
        return;
      }

      const file = selected[0];
      const ext = file.name.split(".").pop()?.toLowerCase();

      if (ext !== "csv") {
        showToast({
          type: "error",
          title: "Invalid file type",
          message: `"${file.name}" is not a .csv file.`,
        });
        return;
      }

      setUploading(true);
      try {
        const res = await uploadFile(file, "lov");

        if (!res.ok) {
          showToast({
            type: "error",
            title: "Upload failed",
            message: res.error || `Failed to upload "${file.name}".`,
          });
          return;
        }

        const stored = res.data?.filename;

        if (!stored) {
          showToast({
            type: "error",
            title: "Upload failed",
            message: "The server did not return a filename for the upload.",
          });
          return;
        }

        onChange?.(stored);

        showToast({
          type: "success",
          title: value ? "LOV replaced" : "LOV attached",
          message: `"${file.name}" will be used by this job.`,
        });
      } catch {
        showToast({
          type: "error",
          title: "Upload failed",
          message: `"${file.name}" could not be uploaded.`,
        });
      } finally {
        setUploading(false);
      }
    },
    [onChange, showToast, value]
  );

  const onFileChange = (e) => {
    handleUpload(Array.from(e.target.files));
    e.target.value = "";
  };

  /* ── Drag & drop ───────────────────────────────────────────── */
  const onDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onDragLeave = () => setDragOver(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleUpload(Array.from(e.dataTransfer.files));
  };

  /* ── Remove ────────────────────────────────────────────────── */
  // Detaches the file from the job rather than deleting it from storage: the
  // job may not exist yet, and another job may already be using the same file.
  const handleRemove = useCallback(() => {
    onChange?.(null);
    showToast({
      type: "success",
      title: "LOV removed",
      message: "This job will run without a reference list.",
    });
  }, [onChange, showToast]);

  const canEdit = !readOnly && typeof onChange === "function";

  /* ── Render ────────────────────────────────────────────────── */
  return (
    <div className={`lov-panel ${compact ? "lov-panel--compact" : ""} ${className}`}>
      <div className="lov-panel-header">
        <div className="lov-panel-title">
          <FileText size={16} aria-hidden="true" />
          <span>LOV Reference File</span>
          <span className="pill lov-optional-pill">Optional</span>
        </div>
        {!readOnly && (
          <a
            href={sampleLovUrl()}
            className="btn btn-ghost btn-sm lov-sample-link"
            download
          >
            <Download size={14} aria-hidden="true" />
            Sample LOV
          </a>
        )}
      </div>

      {/* Help text */}
      <p className="lov-help">
        Only needed for <strong>DQ8</strong> rules, and one file covers the whole
        job: each <strong>column header</strong> is a LOV name - the same value
        the rule carries in its Rule Parameters cell (e.g.{" "}
        <code>Customer.CustomerName</code>) - and the cells below it are that
        column&apos;s allowed values. Columns are independent, so a shorter list
        just leaves the rest of its column blank.
      </p>

      {/* Upload zone - only while the job has no file yet */}
      {canEdit && !value && (
        <div
          className={`lov-dropzone ${dragOver ? "lov-dropzone--active" : ""} ${uploading ? "lov-dropzone--uploading" : ""}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={onFileChange}
            className="lov-file-input"
            aria-label="Upload the LOV CSV for this job"
          />
          {uploading ? (
            <div className="lov-dropzone-content">
              <Loader2 size={20} className="spin" aria-hidden="true" />
              <span>Uploading…</span>
            </div>
          ) : (
            <div className="lov-dropzone-content">
              <UploadCloud size={20} aria-hidden="true" />
              <span>
                Drop one <code>.csv</code> here or <strong>browse</strong>
              </span>
            </div>
          )}
        </div>
      )}

      {/* The job's file */}
      {jobMode &&
        (value ? (
          <div className="lov-file-list">
            <div className="lov-file-row">
              <div className="lov-file-info">
                <span
                  className="lov-file-name"
                  title={entry?.display_name || value}
                >
                  {entry?.display_name || value}
                </span>
                {loading ? (
                  <span className="lov-file-meta">Reading columns…</span>
                ) : !entry || entry.lovs.length === 0 ? (
                  <span className="lov-file-meta lov-file-meta--warn">
                    No column headers found - is this a valid LOV CSV?
                  </span>
                ) : (
                  <span className="lov-file-meta">
                    {entry.lovs.length} LOV
                    {entry.lovs.length !== 1 ? "s" : ""}:{" "}
                    {entry.lovs
                      .map((lov) => `${lov.name} (${lov.values_count})`)
                      .join(", ")}
                  </span>
                )}
              </div>
              {canEdit && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm lov-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemove();
                  }}
                  title="Remove this LOV from the job"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="lov-empty">
            No LOV file for this job.{" "}
            {canEdit && "Add one only if it uses DQ8 rules."}
          </div>
        ))}
    </div>
  );
}
