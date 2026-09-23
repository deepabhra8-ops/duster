import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildKey,
  clearAll,
  invalidate,
  isCacheable,
  readEntry,
  resourcePrefix,
  writeEntry,
  __reset,
} from "./pageCache.js";
import { PAGE_CACHE_MAX_ENTRIES, PAGE_CACHE_TTL_MS } from "../constants/appConfig.js";

beforeEach(() => {
  window.sessionStorage.clear();
  __reset();
});

afterEach(() => vi.useRealTimers());

describe("keys", () => {
  it("scopes per user, so one user cannot read another's entries", () => {
    writeEntry(buildKey("alice", "jobs", { page: 1 }), ["alice job"]);

    expect(readEntry(buildKey("bob", "jobs", { page: 1 }))).toBeNull();
    expect(readEntry(buildKey("alice", "jobs", { page: 1 })).data).toEqual(["alice job"]);
  });

  it("is order-independent, so one query cannot produce two entries", () => {
    expect(buildKey("a", "jobs", { page: 1, search: "x" })).toBe(
      buildKey("a", "jobs", { search: "x", page: 1 })
    );
  });

  it("ignores empty params so a blank filter is not part of the identity", () => {
    expect(buildKey("a", "jobs", { page: 1, search: "" })).toBe(
      buildKey("a", "jobs", { page: 1 })
    );
  });
});

describe("what may never be cached", () => {
  it.each([
    "/connections/abc/reveal",
    "/test-connection",
    "/job/123/profile-map",
    "/connections/abc/schemas",
    "/connections/abc/tables",
    "/connections/abc/columns",
    "job:123",
  ])("refuses %s", (resource) => {
    expect(isCacheable(resource)).toBe(false);
  });

  it("allows the list endpoints it exists for", () => {
    expect(isCacheable("jobs")).toBe(true);
    expect(isCacheable("connections")).toBe(true);
    expect(isCacheable("dashboard")).toBe(true);
  });
});

describe("freshness", () => {
  it("treats an entry past its TTL as a miss", () => {
    vi.useFakeTimers();
    const key = buildKey("a", "dashboard");
    writeEntry(key, { total: 1 });

    expect(readEntry(key)).not.toBeNull();

    vi.advanceTimersByTime(PAGE_CACHE_TTL_MS + 1000);

    expect(readEntry(key)).toBeNull();
  });
});

describe("invalidation", () => {
  it("drops every cached page of a list, not just the one on screen", () => {
    for (const page of [1, 2, 3]) {
      writeEntry(buildKey("a", "jobs", { step: "1", page }), [`page ${page}`]);
    }
    writeEntry(buildKey("a", "jobs", { step: "3", page: 1 }), ["validator"]);
    writeEntry(buildKey("a", "dashboard"), { total: 3 });

    invalidate(resourcePrefix("a", "jobs"));

    expect(readEntry(buildKey("a", "jobs", { step: "1", page: 2 }))).toBeNull();
    expect(readEntry(buildKey("a", "jobs", { step: "3", page: 1 }))).toBeNull();
    expect(readEntry(buildKey("a", "dashboard"))).not.toBeNull();
  });

  it("clearAll leaves nothing behind", () => {
    writeEntry(buildKey("a", "jobs", { page: 1 }), [1]);
    writeEntry(buildKey("b", "connections"), [2]);

    clearAll();

    expect(readEntry(buildKey("a", "jobs", { page: 1 }))).toBeNull();
    expect(readEntry(buildKey("b", "connections"))).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
  });
});

describe("bounds", () => {
  it("evicts oldest beyond the cap, so deep paging cannot fill storage", () => {
    for (let page = 1; page <= PAGE_CACHE_MAX_ENTRIES + 5; page += 1) {
      writeEntry(buildKey("a", "jobs", { page }), [page]);
    }

    expect(readEntry(buildKey("a", "jobs", { page: 1 }))).toBeNull();
    expect(readEntry(buildKey("a", "jobs", { page: PAGE_CACHE_MAX_ENTRIES + 5 }))).not.toBeNull();
  });

  it("degrades to no-cache when storage throws instead of breaking the page", () => {
    const spy = vi.spyOn(window.sessionStorage, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });

    const key = buildKey("a", "jobs", { page: 1 });
    expect(() => writeEntry(key, [1])).not.toThrow();
    expect(readEntry(key).data).toEqual([1]);

    spy.mockRestore();
  });
});
