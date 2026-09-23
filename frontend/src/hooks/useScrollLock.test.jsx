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
