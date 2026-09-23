/**
 * JobErrorButton.jsx - the "why did this fail?" affordance on the Profile
 * Mapper and Validator job lists.
 *
 * A failed job showed only an "Error" pill. The reason was already in the
 * database - jobs.error_message, written by the reconciler and the
 * stuck-submission sweep, and returned by GET /api/job/{id} - but nothing on
 * the list page ever asked for it, so the only way to find out what went wrong
 * was to open the job.
 *
 * Deliberately fetched on click rather than with the list: an error message can
 * be a full Glue stack trace, and attaching one to every row of every page of
 * the list would bloat a response that is otherwise a few hundred bytes per job
 * - for a detail almost every row never needs shown. The trade is a brief
 * spinner on the button, which is what the `loading` state below is for.
 *
 * Rendered beside the Error pill, so it reads as part of the status rather than
 * as another row action - the action buttons live in their own column.
 */
import { useEffect, useState } from "react";
import { AlertCircle, Check, Copy } from "lucide-react";
import { fetchJob } from "../api/api.js";
import { useScrollLock } from "../hooks/useScrollLock.js";
import ModalPortal from "./ModalPortal.jsx";

/** Shown when the job failed but the row carries no message - a job killed
 *  outside the app's own error paths can genuinely have nothing recorded. */
const NO_MESSAGE =
  "This job is marked as failed, but no error message was recorded for it.";

/**
 * Copy without the async Clipboard API. Returns whether it worked.
 *
 * navigator.clipboard is a SECURE-CONTEXT api: on a plain-http origin it is not
 * merely permission-denied, it is undefined. The app is served over http from
 * an ALB hostname, so the Copy button was calling a method that did not exist,
 * throwing, and falling into a branch that only selected the text - no copy, no
 * tick, nothing that looked like it had done anything.
 *
 * document.execCommand("copy") is deprecated, and it is also the only thing
 * that works on that origin, so it stays until the deployment is behind https.
 */
function copyViaExecCommand(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  // readonly so a mobile keyboard does not appear; off-screen rather than
  // display:none, which would make it unselectable and so uncopyable.
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);

  // Whatever the user had selected is restored afterwards - copying a stack
  // trace should not silently destroy a selection they were working with.
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

  /* "Copied" is a transient acknowledgement, not state worth keeping: it clears
     itself, and the timer is cancelled if the dialog closes or the component
     unmounts first, so nothing calls setState on a gone component. */
  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  // Freeze the page behind the overlay, like every other modal in the app.
  useScrollLock(open);

  /* Three routes, tried in order of how well they behave, and the button only
     claims success when a copy actually happened. */
  async function copyMessage() {
    if (!message) return;

    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(message);
        setCopied(true);
        return;
      } catch {
        /* Present but refused - permission, or a document that is not focused.
           Fall through rather than give up. */
      }
    }

    if (copyViaExecCommand(message)) {
      setCopied(true);
      return;
    }

    /* Nothing could copy. Select the text so one Ctrl+C still gets it out, and
       deliberately do NOT show the tick - a "Copied" over an empty clipboard is
       worse than no feedback, because the user walks away believing they have
       the trace. */
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
      // The fetch failing is itself worth saying plainly - silently showing
      // "no message recorded" would blame the job for a network problem.
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
                {/* A stack trace is something you paste into a ticket or a
                    search box, so copying it is the most likely next action
                    after reading it. Nothing to copy until the fetch lands. */}
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
                /* <pre>, not <p>: these messages arrive with the line breaks
                   and indentation of a stack trace, and collapsing them into a
                   paragraph is what makes a Glue failure unreadable. */
                <pre className="job-error-text">{message}</pre>
              )}
            </div>
            {/* No footer button. The header's x already closes this, and unlike
                a wizard there is nothing here to confirm or cancel - the dialog
                only reports. A second control doing the same thing just reads
                as a choice the reader has to make. Escape and a click on the
                backdrop close it too. */}
          </div>
        </div>
        </ModalPortal>
      ) : null}
    </>
  );
}
