import { useEffect, useState } from "react";
import { AlertTriangle, Database, Pencil, X } from "lucide-react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import ModalPortal from "../ModalPortal.jsx";
import DatabaseFields from "./DatabaseFields.jsx";
import DatabaseFieldsSkeleton from "./DatabaseFieldsSkeleton.jsx";
import { revealConnection } from "../../api/api.js";
import "../../styles/new-job-modal.css";

export default function ViewConnectionModal({ open, onClose, connection, onEdit, dbTypeLabel }) {
  const [details, setDetails] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !connection) return;

    let cancelled = false;
    setDetails({});
    setError("");
    setLoading(true);

    revealConnection(connection.id).then(({ ok, data, error: err }) => {
      if (cancelled) return;
      setLoading(false);
      if (!ok) {
        setError(err || "Failed to load connection details");
        return;
      }
      setDetails(data?.data?.connection_details || {});
    });

    return () => {
      cancelled = true;
    };
  }, [open, connection]);

  useScrollLock(open);

  if (!open) return null;

  return (
    <ModalPortal>
      <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="njm njm-wide modal-box wizard-box wizard-box-sm">
          <div className="njm-header">
            <div className="njm-header-main">
              <span className="njm-header-icon" aria-hidden="true">
                <Database size={20} />
              </span>
              <span>
                <span className="njm-title">Connection Details</span>
                <span className="njm-subtitle">{connection?.name}</span>
              </span>
            </div>
            <button type="button" className="njm-close" onClick={onClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          <div className="njm-body">
            <div className="njm-stack">
              <div className="njm-field">
                <label className="njm-label">Connection Name</label>
                <input type="text" value={connection?.name || ""} readOnly disabled />
              </div>

              <div className="njm-field">
                <label className="njm-label">Description</label>
                <textarea value={connection?.description || ""} readOnly disabled placeholder="—" />
              </div>

              <div className="njm-field">
                <label className="njm-label">Database Type</label>
                <input type="text" value={dbTypeLabel || connection?.db_type || ""} readOnly disabled />
              </div>

              {connection?.db_type ? (
                loading ? (
                  <DatabaseFieldsSkeleton dbType={connection.db_type} />
                ) : (
                  <DatabaseFields dbType={connection.db_type} details={details} onChange={() => {}} enhanced readOnly />
                )
              ) : null}
            </div>

            {error ? (
              <div className="njm-alert" role="alert">
                <AlertTriangle size={16} aria-hidden="true" />
                <span>{error}</span>
              </div>
            ) : null}
          </div>

          <div className="njm-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                onClose();
                onEdit?.(connection);
              }}
            >
              <Pencil size={14} aria-hidden="true" />
              Edit
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
