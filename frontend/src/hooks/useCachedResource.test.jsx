/**
 * useCachedResource - the stale-while-revalidate contract.
 *
 * The point of the hook is that a returning visit paints from cache instead of
 * a skeleton, and that a slow response can never overwrite a newer one.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCachedResource } from "./useCachedResource.js";
import { buildKey, writeEntry, __reset } from "../utils/pageCache.js";

function Probe({ cacheKey, fetcher }) {
  const { data, loading, refreshing } = useCachedResource({ key: cacheKey, fetcher });
  return (
    <div>
      <span data-testid="data">{JSON.stringify(data)}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="refreshing">{String(refreshing)}</span>
    </div>
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  __reset();
});

describe("first visit", () => {
  it("shows the loading state, then the data", async () => {
    const key = buildKey("a", "jobs", { page: 1 });
    const fetcher = vi.fn().mockResolvedValue({ ok: true, data: { jobs: ["x"] } });

    render(<Probe cacheKey={key} fetcher={fetcher} />);

    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("data")).toHaveTextContent('{"jobs":["x"]}');
  });
});

describe("returning visit", () => {
  it("paints from cache with no skeleton, then revalidates in the background", async () => {
    const key = buildKey("a", "jobs", { page: 1 });
    writeEntry(key, { jobs: ["cached"] });

    const fetcher = vi.fn().mockResolvedValue({ ok: true, data: { jobs: ["fresh"] } });

    render(<Probe cacheKey={key} fetcher={fetcher} />);

    // The whole point: data is on screen immediately and loading is already false.
    expect(screen.getByTestId("loading")).toHaveTextContent("false");
    expect(screen.getByTestId("data")).toHaveTextContent("cached");

    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("fresh"));
  });
});

describe("resilience", () => {
  it("keeps the cached data on screen when a revalidation fails", async () => {
    const key = buildKey("a", "jobs", { page: 1 });
    writeEntry(key, { jobs: ["cached"] });

    const fetcher = vi.fn().mockResolvedValue({ ok: false, error: "Cannot reach API" });

    render(<Probe cacheKey={key} fetcher={fetcher} />);

    await waitFor(() => expect(screen.getByTestId("refreshing")).toHaveTextContent("false"));
    // A failed background refresh must not blank a page that was working.
    expect(screen.getByTestId("data")).toHaveTextContent("cached");
  });

  it("dedupes concurrent mounts on one key into a single request", async () => {
    const key = buildKey("a", "connections");
    const fetcher = vi.fn().mockResolvedValue({ ok: true, data: ["one"] });

    render(
      <>
        <Probe cacheKey={key} fetcher={fetcher} />
        <Probe cacheKey={key} fetcher={fetcher} />
      </>
    );

    await waitFor(() => expect(screen.getAllByTestId("loading")[0]).toHaveTextContent("false"));

    // Two components, one key, one network call.
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
