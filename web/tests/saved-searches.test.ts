import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  loadSavedSearches,
  readSearches,
  savedSearch,
  saveSavedSearches,
  searchName,
  searchOf,
} from "../src/saved-searches";
import { exactly, NO_FILTERS, typed } from "../src/search";

describe("saved searches", () => {
  const search = {
    query: "gaussian splatting",
    filters: {
      ...NO_FILTERS,
      authors: [exactly("Hao Li")],
      affiliations: [typed("mit")],
      venues: ["ECCV 2026"],
    },
  };

  it("keep the words and filters of a view, which read back", () => {
    const saved = savedSearch(search);
    expect(saved).toEqual({
      name: "gaussian splatting · by Hao Li · at mit · ECCV 2026",
      search: "?q=gaussian+splatting&by=Hao+Li&aff=mit&venue=ECCV+2026",
    });
    expect(saved && searchOf(saved)).toEqual(search);
  });

  it("are nothing for a view without words or filters", () => {
    expect(savedSearch({ query: "  ", filters: NO_FILTERS })).toBeNull();
  });

  it("name every kind of filter", () => {
    expect(
      searchName({
        query: "",
        filters: {
          ...NO_FILTERS,
          venues: ["*"],
          subject: "Robotics (cs.RO)",
          excludeCrossLists: true,
          withCode: true,
        },
      }),
    ).toBe("any venue · Robotics (cs.RO) · no cross-lists · with code");
  });

  it("name several values of a filter as a choice (SRCH-21)", () => {
    const filters = {
      ...NO_FILTERS,
      authors: [exactly("Hao Li"), exactly("Kaiming He")],
      affiliations: [exactly("MIT"), typed("stanford")],
      venues: ["CVPR*", "ICCV 2025"],
    };
    const saved = savedSearch({ query: "", filters });
    expect(saved?.name).toBe(
      "by Hao Li or Kaiming He · at MIT or stanford · CVPR, any year or ICCV 2025",
    );
    expect(saved && searchOf(saved)).toEqual({ query: "", filters });
  });

  it("read only what is a search, once", () => {
    expect(
      readSearches([
        { name: "a", search: "?q=a" },
        { name: "a again", search: "?q=a" },
        { name: "no query string", search: "q=b" },
        "junk",
        null,
      ]),
    ).toEqual([{ name: "a again", search: "?q=a" }]);
    expect(readSearches({ not: "a list" })).toEqual([]);
  });

  describe("in storage", () => {
    beforeEach(() => {
      const stored = new Map<string, string>();
      vi.stubGlobal("localStorage", {
        getItem: (key: string) => stored.get(key) ?? null,
        setItem: (key: string, value: string) => stored.set(key, value),
      });
    });
    afterEach(() => vi.unstubAllGlobals());

    it("are none, and not saved, when the browser refuses its storage", () => {
      vi.stubGlobal("localStorage", {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
      });
      expect(loadSavedSearches()).toEqual([]);
      expect(saveSavedSearches([{ name: "a", search: "?q=a" }])).toBe(false);
    });

    it("are kept, and read back", () => {
      expect(loadSavedSearches()).toEqual([]);
      expect(saveSavedSearches([{ name: "a", search: "?q=a" }])).toBe(true);
      expect(loadSavedSearches()).toEqual([{ name: "a", search: "?q=a" }]);
    });
  });
});
