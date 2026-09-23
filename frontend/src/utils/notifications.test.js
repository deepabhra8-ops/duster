import { describe, expect, it } from "vitest";

import { isInternalPath, notificationTone } from "./notifications.js";

describe("isInternalPath", () => {
  it.each(["/", "/validator/abc", "/profile-mapper/1?tab=log", "/a#frag"])("accepts %s", (link) => {
    expect(isInternalPath(link)).toBe(true);
  });

  /* Each of these would leave the app if handed to a browser. */
  it.each([
    ["a full URL", "https://evil.example"],
    ["a protocol-relative URL", "//evil.example"],
    ["a backslash, which browsers read as a slash", "/\\evil.example"],
    ["a javascript: URL", "javascript:alert(1)"],
    ["a relative path", "relative/path"],
    ["an empty string", ""],
    ["a tab, which browsers strip from URLs (-> //)", "/\t/evil.example"],
    ["a newline, likewise", "/\n/evil.example"],
    ["a NUL", "/ok\u0000"],
  ])("refuses %s", (_label, link) => {
    expect(isInternalPath(link)).toBe(false);
  });

  it.each([null, undefined, 5, {}, ["/a"]])("refuses a non-string (%s)", (link) => {
    expect(isInternalPath(link)).toBe(false);
  });
});

describe("notificationTone", () => {
  it("maps the job types to a tone", () => {
    expect(notificationTone("job_done")).toBe("success");
    expect(notificationTone("job_error")).toBe("error");
    expect(notificationTone("job_cancelled")).toBe("warn");
  });

  it("falls back to neutral for a type it has never heard of, so a new type needs no UI change", () => {
    expect(notificationTone("something_new")).toBe("info");
    expect(notificationTone(undefined)).toBe("info");
  });
});
