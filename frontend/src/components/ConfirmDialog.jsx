/**
 * ConfirmDialog.jsx - Shared confirmation dialog for destructive actions.
 *
 * Replaces window.confirm() on all three destructive paths (delete connection,
 * delete profile mapper job, delete validator job). Built on the existing
 * .modal-overlay/.modal-box/.modal-header/.wizard-footer shell so it shares
 * the same visual language as every other modal in the app.
 *
 * Design choices:
 *   - Cancel button is autoFocus'd - the safe default prevents accidental
 *     confirm on Enter without reading the dialog.
 *   - Esc closes and cancels (same as AlertModal).
 *   - Overlay click cancels.
 *   - `danger` prop switches the confirm button to btn-danger (red).
 *   - `subject` renders bold in the title row so the user knows exactly
 *     what they're deleting - no ambiguity.
 */
import { useEffect, useRef } from "react";
import { useScrollLock } from "../hooks/useScrollLock.js";
import ModalPortal from "./ModalPortal.jsx";

export default function ConfirmDialog({
  open,
  title = "Are you sure?",
  subject,
  message,
  confirmLabel = "Confirm",
  danger = false,
  onConfirm,
  onCancel,
}) {
  const cancelRef = useRef(null);

  /* Esc to cancel */
  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  /* Auto-focus cancel on open */
  useEffect(() => {
    if (open && cancelRef.current) {
      cancelRef.current.focus();
    }
  }, [open]);

  // Freeze the page behind the overlay - see the hook for why a plain
  // body overflow:hidden is not enough (nesting, scrollbar layout shift).
  useScrollLock(open);

  if (!open) return null;

  return (
    <ModalPortal>
      <div
        className="modal-overlay"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-desc"
        onClick={(e) => e.target === e.currentTarget && onCancel()}
      >
        <div className="modal-box modal-box-sm">
          <div className="modal-header" id="confirm-dialog-title">
            <span>
              {title}
              {subject && (
                <>
                  {" "}
                  <strong style={{ fontWeight: 700 }}>&ldquo;{subject}&rdquo;</strong>
                </>
              )}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onCancel}
              aria-label="Cancel and close"
            >
              <span
                className="modal-close-icon"
                style={{ "--icon-src": "url(/icons/close.svg)" }}
                aria-hidden="true"
              />
            </button>
          </div>

          <div className="modal-body" id="confirm-dialog-desc">
            {message && (
              <p style={{ fontSize: "var(--text-base)", lineHeight: "var(--leading-normal)", color: "var(--dgray)" }}>
                {message}
              </p>
            )}
          </div>

          <div className="wizard-footer">
            {/* Cancel focused by default - safe action is the keyboard default */}
            <button
              ref={cancelRef}
              type="button"
              className="btn btn-ghost"
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              type="button"
              className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
              onClick={onConfirm}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
