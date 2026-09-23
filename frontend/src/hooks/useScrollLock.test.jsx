/**
 * useScrollLock - the page behind an open modal must not scroll.
 *
 * The two cases a plain `body { overflow: hidden }` gets wrong, and which this
 * hook exists to handle:
 *
 *   - Nesting. A wizard can raise a ConfirmDialog on top of itself. If each
 *     modal unlocked on unmount, closing the inner one would release the lock
 *     while the outer modal is still open, and the page would start scrolling
 *     underneath it again.
 *   - Layout shift. Hiding the scrollbar reclaims its width, so the page jumps
 *     sideways as a modal opens unless that width is replaced with padding.
 */
import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useScrollLock } from "./useScrollLock.js";

function Modal({ open }) {
  useScrollLock(open);
  return null;
}

afterEach(() => {
  document.body.style.overflow = "";
  document.body.style.paddingRight = "";
});

describe("locking", () => {
  it("freezes the body while open", () => {
    render(<Modal open />);
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("does nothing while closed", () => {
    render(<Modal open={false} />);
    expect(document.body.style.overflow).toBe("");
  });

  it("releases on close", () => {
    const { rerender } = render(<Modal open />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<Modal open={false} />);
    expect(document.body.style.overflow).toBe("");
  });

  it("releases on unmount, so navigating away cannot strand the lock", () => {
    const { unmount } = render(<Modal open />);
    unmount();
    expect(document.body.style.overflow).toBe("");
  });
});

describe("nesting", () => {
  it("stays locked until the LAST modal closes", () => {
    const { rerender } = render(
      <>
        <Modal open />
        <Modal open />
      </>
    );
    expect(document.body.style.overflow).toBe("hidden");

    // Inner dialog closes; the outer modal is still open.
    rerender(
      <>
        <Modal open />
        <Modal open={false} />
      </>
    );
    expect(document.body.style.overflow).toBe("hidden");

    rerender(
      <>
        <Modal open={false} />
        <Modal open={false} />
      </>
    );
    expect(document.body.style.overflow).toBe("");
  });
});

describe("restoring", () => {
  it("puts back whatever overflow the page already had", () => {
    document.body.style.overflow = "scroll";

    const { rerender } = render(<Modal open />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<Modal open={false} />);
    expect(document.body.style.overflow).toBe("scroll");
  });
});
