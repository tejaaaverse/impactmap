import { describe, expect, it } from "vitest";
import {
  formatDuration,
  formatPercent,
  formatRelative,
  parseList,
  shortenPath,
  statusTone,
} from "./format";

describe("formatDuration", () => {
  it("formats sub-second, second and minute durations", () => {
    expect(formatDuration(0.4)).toBe("<1 ms");
    expect(formatDuration(42)).toBe("42 ms");
    expect(formatDuration(1500)).toBe("1.50 s");
    expect(formatDuration(65_000)).toBe("1m 5s");
  });

  it("renders missing values as an em dash", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("formats percentages with configurable precision", () => {
    expect(formatPercent(72.456)).toBe("72.5%");
    expect(formatPercent(72.456, 0)).toBe("72%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("shortenPath", () => {
  it("keeps short paths intact and preserves file names for long paths", () => {
    expect(shortenPath("calculator/core.py", 48)).toBe("calculator/core.py");
    const shortened = shortenPath(
      "package/with/a/very/long/nested/directory/structure/module.py",
      32,
    );
    expect(shortened).toContain("module.py");
    expect(shortened.length).toBeLessThanOrEqual(32);
  });
});

describe("statusTone", () => {
  it("maps engine statuses to semantic tones", () => {
    expect(statusTone("completed")).toBe("emerald");
    expect(statusTone("failed")).toBe("rose");
    expect(statusTone("fallback")).toBe("amber");
    expect(statusTone("running")).toBe("sky");
    expect(statusTone("unknown-value")).toBe("slate");
  });
});

describe("parseList", () => {
  it("splits, trims and drops empty entries", () => {
    expect(parseList(" a, b ,,c ")).toEqual(["a", "b", "c"]);
  });
});

describe("formatRelative", () => {
  it("returns a relative label for recent timestamps", () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelative(fiveMinutesAgo)).toMatch(/^(5m|4m) ago$/);
  });
});
