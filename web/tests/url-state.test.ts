import { describe, expect, it } from "vitest";
import { DEFAULT_STATE, readState, writeState } from "../src/url-state";

describe("url state", () => {
  it("omits defaults", () => {
    expect(writeState(DEFAULT_STATE)).toBe("");
  });

  it("round-trips a full state", () => {
    const state = {
      ...DEFAULT_STATE,
      query: 'gaussian "novel view"',
      category: "cs.CV",
      range: "20" as const,
      sort: "newest" as const,
      view: "reading-list" as const,
      filters: { excludeCrossLists: true, author: "Ada", affiliation: "MIT", subject: null },
    };
    expect(readState(writeState(state))).toEqual(state);
  });

  it("falls back to defaults on invalid values", () => {
    expect(readState("?range=42&sort=weird")).toEqual(DEFAULT_STATE);
  });
});
