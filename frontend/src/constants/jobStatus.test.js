import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { STATUS_PILL, STATUS_PROGRESS_COLOR } from "./jobStatus.js";

const STATUSES = ["draft", "queued", "running", "cancelling", "done", "error", "cancelled"];

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const globalCss = read("../styles/global.css");
const chromeCss = read("../styles/app-chrome.css");
const chartSource = read("../components/JobStatusChart.jsx");

const colourOf = (status) =>
  globalCss.match(new RegExp(`--status-${status}:\\s*(#[0-9A-Fa-f]{6})`))?.[1]?.toUpperCase();

describe("job status colours", () => {
  it("maps every status to a pill class and a colour variable", () => {
    expect(Object.keys(STATUS_PILL).sort()).toEqual([...STATUSES].sort());
    expect(Object.keys(STATUS_PROGRESS_COLOR).sort()).toEqual([...STATUSES].sort());
  });

  it("defines one colour per status", () => {
    for (const status of STATUSES) {
      expect(colourOf(status), `--status-${status}`).toBeDefined();
    }
  });

  it("gives every status a colour no other status has", () => {
    const colours = STATUSES.map(colourOf);
    expect(new Set(colours).size).toBe(STATUSES.length);
  });

  it("points the pill and the progress bar at the same status colour", () => {
    for (const status of STATUSES) {
      expect(STATUS_PROGRESS_COLOR[status]).toBe(`--status-${status}`);
      expect(STATUS_PILL[status]).toBe(`pill-status-${status}`);
      expect(chromeCss).toMatch(
        new RegExp(`\\.pill-status-${status}\\s*\\{[^}]*background:\\s*var\\(--status-${status}\\)`)
      );
    }
  });

  it("has no colour list of its own in the chart", () => {
    expect(chartSource).toContain("STATUS_PROGRESS_COLOR");
    expect(chartSource).not.toMatch(/#[0-9A-Fa-f]{6}/);
  });
});
