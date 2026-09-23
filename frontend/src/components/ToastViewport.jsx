/**
 * ToastViewport.jsx - fixed stack of toast notifications (ToastContext.jsx).
 *
 * Each toast auto-dismisses after its own `duration`, shown as a shrinking
 * bar (.toast-progress-fill's CSS animation, global.css) rather than a
 * separate JS-driven progress state - hovering pauses both that animation
 * and the underlying dismiss timer (handleMouseEnter/Leave below), resuming
 * both together on mouse-leave.
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

/**
 * Pin the stack under the topbar's notification bell.
 *
 * Toasts used to sit at a hardcoded top/right and slide in sideways, so they
 * read as arriving from nothing. Anchoring them to the bell - and scaling them
 * out of it - makes the bell the visible source of every notification, which is
 * what a user already expects that icon to mean.
 *
 * Measured at runtime rather than hardcoded: the bell's position depends on the
 * logo beside it and the sidebar width, both of which can change. Falls back to
 * the previous fixed corner if the bell is not on screen (e.g. the login page,
 * which renders no topbar).
 */
function useBellAnchor(toastCount) {
  const [anchor, setAnchor] = useState(null);

  useEffect(() => {
    function measure() {
      const bell = document.querySelector(".notification-btn");
      if (!bell) {
        setAnchor(null);
        return;
      }
      const rect = bell.getBoundingClientRect();
      setAnchor({
        // Right-align the stack to the bell's own right edge.
        right: Math.max(12, window.innerWidth - rect.right),
        top: Math.round(rect.bottom + 10),
      });
    }

    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
    // Re-measured whenever a toast appears, not just on mount: this component
    // lives at the app root, so it is already mounted while the login page is
    // showing - and that page renders no topbar. Measuring once would pin the
    // stack to the fallback corner for the rest of the session.
  }, [toastCount]);

  return anchor;
}

/* lucide, not the emoji this used to render. Emoji are the OS's, not the app's:
   they sat at a different weight and colour on every platform, and ✅/❌ in
   particular render as full-colour glyphs that no theme can tint. These take
   currentColor from their tile, so a toast matches the cards and banners the
   rest of the app is built from.

   One icon per meaning rather than one per colour: a filled check for something
   that finished, a filled cross for something that failed, a triangle for a
   warning (the shape convention people already read as "caution"), and an i for
   plain information. */
const TOAST_ICON = {
  success: CheckCircle2,
  error: XCircle,
  warn: AlertTriangle,
  info: Info,
};

function ToastItem({ toast, onDismiss }) {
  const [paused, setPaused] = useState(false);
  const remainingMs = useRef(toast.duration);
  const startedAt = useRef(Date.now());
  const timerRef = useRef(null);

  useEffect(() => {
    if (toast.leaving || paused) return undefined;
    startedAt.current = Date.now();
    timerRef.current = setTimeout(() => onDismiss(toast.id), remainingMs.current);
    return () => clearTimeout(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, toast.leaving]);

  function handleMouseEnter() {
    if (toast.leaving || paused) return;
    clearTimeout(timerRef.current);
    remainingMs.current = Math.max(0, remainingMs.current - (Date.now() - startedAt.current));
    setPaused(true);
  }

  function handleMouseLeave() {
    if (toast.leaving || !paused) return;
    setPaused(false);
  }

  const Icon = TOAST_ICON[toast.type] || TOAST_ICON.info;

  return (
    <div
      className={`toast toast-${toast.type}${toast.leaving ? " toast-leaving" : ""}`}
      role={toast.type === "error" ? "alert" : "status"}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <span className="toast-icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <div className="toast-text">
        {toast.title ? <div className="toast-title">{toast.title}</div> : null}
        {toast.message ? <div className="toast-message">{toast.message}</div> : null}
      </div>
      <button
        type="button"
        className="toast-close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <X size={14} aria-hidden="true" />
      </button>
      <div className="toast-progress">
        <div
          className="toast-progress-fill"
          style={{ animationDuration: `${toast.duration}ms`, animationPlayState: paused ? "paused" : "running" }}
        />
      </div>
    </div>
  );
}

export default function ToastViewport({ toasts, onDismiss }) {
  const anchor = useBellAnchor(toasts.length);

  if (!toasts.length) return null;

  return (
    <div
      className="toast-viewport"
      style={anchor ? { top: anchor.top, right: anchor.right } : undefined}
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
