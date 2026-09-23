/**
 * FilePreviewModal.jsx - Overlay modal that previews the first rows of an
 * uploaded file via previewUpload(kind, filename).
 *
 * Controlled by the parent: render with `open` true and a target
 * { kind, filename }. Closing is handled via onClose (overlay click,
 * close button, or Esc).
 */
import { useEffect, useState } from "react";
import { useScrollLock } from "../hooks/useScrollLock.js";
import { previewUpload } from "../api/api.js";
import { IconError } from "./Icons.jsx";
import ModalPortal from "./ModalPortal.jsx";

export default function FilePreviewModal({ open, kind, filename, onClose }) {
  const [state, setState] = useState({ loading: false, error: null, columns: [], rows: [] });

  useEffect(() => {
    if (!open || !filename) return;
    let cancelled = false;
    setState({ loading: true, error: null, columns: [], rows: [] });
    previewUpload(kind, filename).then(({ ok, data, error }) => {
      if (cancelled) return;
      if (!ok) {
        setState({ loading: false, error: error || "Cannot preview this file.", columns: [], rows: [] });
        return;
      }
      setState({ loading: false, error: null, columns: data.columns || [], rows: data.rows || [] });
    });
    return () => {
      cancelled = true;
    };
  }, [open, kind, filename]);

  // Close on Escape while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Freeze the page behind the overlay - see the hook for why a plain
  // body overflow:hidden is not enough (nesting, scrollbar layout shift).
  useScrollLock(open);

  if (!open) return null;

  const { loading, error, columns, rows } = state;

  return (
    <ModalPortal>
      <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="modal-box">
          <div className="modal-header">
            <span>Preview: {filename}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
              ✕ Close
            </button>
          </div>
          <div style={{ overflow: "auto", maxHeight: "60vh" }}>
            {loading ? (
              <p className="empty-state">Loading…</p>
            ) : error ? (
              <p className="empty-state" style={{ color: "red" }}><IconError style={{ verticalAlign: "text-bottom" }} /> {error}</p>
            ) : (
              <>
                <table className="tbl" style={{ fontSize: "13px" }}>
                  <thead>
                    <tr>
                      {columns.map((col, i) => (
                        <th key={i}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((cell, ci) => (
                          <td key={ci}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length === 50 && (
                  <p className="hint" style={{ marginTop: "8px" }}>
                    Showing first 50 rows only.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
