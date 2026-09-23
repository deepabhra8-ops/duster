import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

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
        right: Math.max(12, window.innerWidth - rect.right),
        top: Math.round(rect.bottom + 10),
      });
    }

    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [toastCount]);

  return anchor;
}

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
