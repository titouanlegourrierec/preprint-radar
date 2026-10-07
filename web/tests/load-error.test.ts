import { describe, expect, it } from "vitest";
import { loadErrorMessage } from "../src/hooks/use-papers";
import { activeFilterCount, exactly, NO_FILTERS, typed } from "../src/search";

describe("loadErrorMessage", () => {
  it("says what a failed fetch means", () => {
    expect(loadErrorMessage(new TypeError("Failed to fetch"))).toBe(
      "the network or the site did not answer",
    );
    expect(loadErrorMessage(new Error("data/index.json: 404"))).toBe("data/index.json: 404");
    expect(loadErrorMessage("odd")).toBe("odd");
  });
});

describe("activeFilterCount", () => {
  it("counts the filters that narrow the papers", () => {
    expect(activeFilterCount(NO_FILTERS)).toBe(0);
    expect(
      activeFilterCount({
        ...NO_FILTERS,
        author: exactly("Ada"),
        affiliation: typed("  "),
        venue: "*",
        withCode: true,
      }),
    ).toBe(3);
  });
});
