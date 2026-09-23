import { useEffect, useState } from "react";
import { AlertCircle, Check, Copy } from "lucide-react";
import { fetchJob } from "../api/api.js";
import { useScrollLock } from "../hooks/useScrollLock.js";
import ModalPortal from "./ModalPortal.jsx";

const NO_MESSAGE =
  "This job is marked as failed, but no error message was recorded for it.";

function copyViaExecCommand(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);

  const selection = document.getSelection();
  const previousRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }

  textarea.remove();
  if (previousRange && selection) {
    selection.removeAllRanges();
    selection.addRange(previousRange);
  }

  return ok;
}

export default function JobErrorButton({ jobId, jobName }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  useScrollLock(open);

  async function copyMessage() {
    if (!message) return;

    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(message);
        setCopied(true);
        return;
      } catch {
      }
    }

    if (copyViaExecCommand(message)) {
      setCopied(true);
      return;
    }

    const pre = document.querySelector(".job-error-text");
    if (!pre) return;
    const range = document.createRange();
    range.selectNodeContents(pre);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  async function showError() {
    setOpen(true);
    setLoading(true);
    setMessage("");
    setCopied(false);

    const { ok, data, error } = await fetchJob(jobId);

    setLoading(false);
    if (!ok) {
      setMessage(error || "Could not load the error message for this job.");
      return;
    }
    setMessage(String(data?.error_message || "").trim() || NO_MESSAGE);
  }

  return (
    <>
      <button
        type="button"
        className="job-error-btn"
        onClick={showError}
        disabled={loading}
        title="View the error for this job"
        aria-label={`View the error for ${jobName || jobId}`}
      >
        {loading ? (
          <span className="spinner" aria-hidden="true" />
        ) : (
          <AlertCircle size={16} aria-hidden="true" />
        )}
      </button>

      {open ? (
        <ModalPortal>
        <div
          className="modal-overlay"
          onClick={(e) => e.target === e.currentTarget && setOpen(false)}
        >
          <div className="modal-box job-error-box">
            <div className="modal-header">
              <span>Job failed{jobName ? ` - ${jobName}` : ""}</span>
              <div className="job-error-actions">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-icon-only"
                  onClick={copyMessage}
                  disabled={loading || !message}
                  aria-label={copied ? "Error message copied" : "Copy error message"}
                  title={copied ? "Copied" : "Copy error message"}
                >
                  {copied ? (
                    <Check size={15} aria-hidden="true" className="job-error-copied" />
                  ) : (
                    <Copy size={15} aria-hidden="true" />
                  )}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                >
                  <span
                    className="modal-close-icon"
                    style={{ "--icon-src": "url(/icons/close.svg)" }}
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div className="job-error-body">
              {loading ? (
                <p className="hint">
                  <span className="spinner" aria-hidden="true" /> Loading the error message…
                </p>
              ) : (
                <pre className="job-error-text">{message}</pre>
              )}
            </div>
          </div>
        </div>
        </ModalPortal>
      ) : null}
    </>
  );
}
