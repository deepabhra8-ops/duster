import { useEffect } from "react";
import { useScrollLock } from "../hooks/useScrollLock.js";
import ModalPortal from "./ModalPortal.jsx";

export default function AlertModal({ open, title = "Notice", message, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useScrollLock(open);

  if (!open) return null;

  return (
    <ModalPortal>
      <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className="modal-box modal-box-sm">
          <div className="modal-header">
            <span>{title}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
              <span className="modal-close-icon" style={{ "--icon-src": "url(/icons/close.svg)" }} aria-hidden="true" />
            </button>
          </div>

          <div style={{ padding: "18px 20px" }}>
            <p style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--dgray)" }}>{message}</p>
          </div>

          <div className="wizard-footer">
            <span />
            <button type="button" className="btn btn-primary" onClick={onClose}>
              OK
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
