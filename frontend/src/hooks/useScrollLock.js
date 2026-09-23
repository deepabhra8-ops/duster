import { useEffect } from "react";

let lockCount = 0;
let previousOverflow = "";
let previousPaddingRight = "";

function lock() {
  lockCount += 1;

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

export function useScrollLock(active) {
  useEffect(() => {
    if (!active) return undefined;

    lock();
    return unlock;
  }, [active]);
}

export default useScrollLock;
