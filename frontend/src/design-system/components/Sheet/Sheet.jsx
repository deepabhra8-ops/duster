import { X } from "lucide-react";

/**
 * A right-side slide-over panel — deliberately not a centered modal, so it never blocks the
 * rest of the page (e.g. a connections grid) behind it. `eyebrow` is the small category label
 * above the title (e.g. "Warehouses / Snowflake"); `titleIcon` sits inline before the title.
 */
export function Sheet({ isOpen, onClose, eyebrow, title, titleIcon, footer, wide, bodyClassName = "sheet-body", children }) {
  if (!isOpen) return null;

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className={`sheet-panel${wide ? " sheet-panel-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="sheet-header">
          <div>
            {eyebrow ? <div className="sheet-eyebrow">{eyebrow}</div> : null}
            <div className="sheet-title">
              {titleIcon}
              {title}
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}>
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        <div className={bodyClassName}>{children}</div>

        {footer ? <div className="sheet-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

export function SheetSection({ title, children }) {
  return (
    <div>
      <div className="sheet-section-title">{title}</div>
      {children}
    </div>
  );
}

export default Sheet;
