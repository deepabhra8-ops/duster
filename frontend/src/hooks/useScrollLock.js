/**
 * useScrollLock.js - freeze the page behind an open modal.
 *
 * Without this the overlay covers the page but the page keeps scrolling under
 * it: a wheel gesture aimed at a modal's own body scrolls the job list behind
 * once the modal hits its end, and on touch the background drifts while the
 * dialog stays put. The user closes the modal and finds themselves somewhere
 * else on the page.
 *
 * Two details that a naive `body { overflow: hidden }` gets wrong:
 *
 *  1. Nesting. Several of these modals can be open at once - a wizard that
 *     raises a ConfirmDialog, for instance. If each one unlocked on unmount,
 *     closing the inner dialog would release the lock while the outer modal is
 *     still open. A module-level count fixes that: the lock lifts when the LAST
 *     locker releases it, not the first.
 *
 *  2. Layout shift. Hiding the scrollbar reclaims its width, so the whole page
 *     jumps sideways as the modal opens and jumps back as it closes. The
 *     scrollbar's width is measured and replaced with equivalent padding, so
 *     nothing moves. Overlay scrollbars (macOS, most touch devices) measure 0,
 *     where this correctly does nothing.
 */
import { useEffect } from "react";

let lockCount = 0;
let previousOverflow = "";
let previousPaddingRight = "";

function lock() {
  lockCount += 1;

  // Only the first locker touches the DOM; the rest just increment.
  if (lockCount > 1) return;

  const { body } = document;
  const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;

  previousOverflow = body.style.overflow;
  previousPaddingRight = body.style.paddingRight;

  body.style.overflow = "hidden";

  if (scrollbarWidth > 0) {
    const current = parseFloat(window.getComputedStyle(body).paddingRight) || 0;
    body.style.paddingRight = `${current + scrollbarWidth}px`;
  }
}

function unlock() {
  lockCount = Math.max(0, lockCount - 1);

  if (lockCount > 0) return;

  const { body } = document;
  body.style.overflow = previousOverflow;
  body.style.paddingRight = previousPaddingRight;
}

/**
 * @param {boolean} active  Lock while true; release when it goes false or the
 *   component unmounts (closing a modal by navigating away still releases it).
 */
export function useScrollLock(active) {
  useEffect(() => {
    if (!active) return undefined;

    lock();
    return unlock;
  }, [active]);
}

export default useScrollLock;
