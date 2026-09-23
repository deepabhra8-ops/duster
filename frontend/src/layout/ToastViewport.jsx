import { Alert } from "../design-system/components/index.js";
import "./ToastViewport.css";

const TONE_BY_TYPE = {
  success: "success",
  warn: "warning",
  error: "danger",
};

export function ToastViewport({ toasts, onDismiss }) {
  if (!toasts.length) return null;

  return (
    <div className="toast-viewport" role="region" aria-label="Notifications">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-item${toast.leaving ? " is-leaving" : ""}`}>
          {TONE_BY_TYPE[toast.type] ? (
            <Alert tone={TONE_BY_TYPE[toast.type]} title={toast.title}>
              {toast.message}
            </Alert>
          ) : (
            <div className="toast-item-neutral">
              <div className="toast-item-title">{toast.title}</div>
              <div className="toast-item-message">{toast.message}</div>
            </div>
          )}
          <button
            type="button"
            className="toast-item-dismiss"
            aria-label="Dismiss notification"
            onClick={() => onDismiss(toast.id)}
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  );
}

export default ToastViewport;
