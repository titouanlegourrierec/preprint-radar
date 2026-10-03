import { describe, expect, it } from "vitest";
import { exactly, typed } from "../src/search";
import { DEFAULT_STATE, isNavigation, readState, writeState } from "../src/url-state";

describe("url state", () => {
  it("omits defaults", () => {
    expect(writeState(DEFAULT_STATE)).toBe("");
  });

  it("round-trips a full state", () => {
    const state = {
      ...DEFAULT_STATE,
      query: 'gaussian "novel view"',
      category: "cs.CV",
      period: { kind: "recent" as const, range: "20" as const },
      sort: "newest" as const,
      view: "reading-list" as const,
      filters: {
        excludeCrossLists: true,
        author: typed("Ada"),
        affiliation: exactly("MIT"),
        subject: null,
        venue: "ECCV 2026",
      },
      paper: "2609.30234",
    };
    expect(readState(writeState(state))).toEqual(state);
  });

  it("keeps clicked names apart from typed text", () => {
    const filters = (author: ReturnType<typeof typed>, affiliation: ReturnType<typeof typed>) =>
      writeState({ ...DEFAULT_STATE, filters: { ...DEFAULT_STATE.filters, author, affiliation } });

    expect(filters(exactly("Hao Li"), exactly("Intel"))).toBe("?by=Hao+Li&at=Intel");
    expect(filters(typed("hao"), typed("intel"))).toBe("?author=hao&aff=intel");
    // Links made before exact filters keep working, as typed text.
    expect(readState("?author=Hao+Li&aff=MIT").filters).toMatchObject({
      author: typed("Hao Li"),
      affiliation: typed("MIT"),
    });
    expect(readState("?by=Hao+Li&author=hao").filters.author).toEqual(exactly("Hao Li"));
  });

  it("round-trips a paper permalink", () => {
    const state = {
      ...DEFAULT_STATE,
      period: { kind: "dates" as const, from: "2026-09-25", to: "2026-09-25" },
      paper: "2609.30234",
    };
    expect(writeState(state)).toBe("?from=2026-09-25&paper=2609.30234");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips a range of dates", () => {
    const state = {
      ...DEFAULT_STATE,
      period: { kind: "dates" as const, from: "2026-09-09", to: "2026-09-18" },
    };
    expect(writeState(state)).toBe("?from=2026-09-09&to=2026-09-18");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("reads a single day and dates given in any order", () => {
    expect(readState("?from=2026-09-09").period).toEqual({
      kind: "dates",
      from: "2026-09-09",
      to: "2026-09-09",
    });
    expect(readState("?from=2026-09-18&to=2026-09-09").period).toEqual({
      kind: "dates",
      from: "2026-09-09",
      to: "2026-09-18",
    });
    expect(
      writeState({
        ...DEFAULT_STATE,
        period: { kind: "dates", from: "2026-09-09", to: "2026-09-09" },
      }),
    ).toBe("?from=2026-09-09");
  });

  it("round-trips the citation sort", () => {
    const state = { ...DEFAULT_STATE, sort: "citations" as const };
    expect(writeState(state)).toBe("?sort=citations");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("reads the about view", () => {
    expect(readState("?view=about").view).toBe("about");
    expect(writeState({ ...DEFAULT_STATE, view: "about" })).toBe("?view=about");
  });

  it("reads the graph view", () => {
    expect(readState("?view=graph").view).toBe("graph");
  });

  it("falls back to defaults on invalid values", () => {
    expect(readState("?range=42&sort=weird")).toEqual(DEFAULT_STATE);
    expect(readState("?from=yesterday&to=2026-13-45")).toEqual(DEFAULT_STATE);
  });
});

describe("highly cited view", () => {
  it("round-trips the view and the archive year", () => {
    const state = { ...DEFAULT_STATE, view: "cited" as const, year: 2017 };

    expect(writeState(state)).toBe("?view=cited&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips the graph of an archive year", () => {
    const state = { ...DEFAULT_STATE, view: "graph" as const, year: 2017 };

    expect(writeState(state)).toBe("?view=graph&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips the rankings of an archive year", () => {
    const state = { ...DEFAULT_STATE, view: "rankings" as const, year: 2017 };

    expect(writeState(state)).toBe("?view=rankings&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("ignores a malformed year", () => {
    expect(readState("?view=cited&year=soon").year).toBeNull();
  });
});

describe("isNavigation", () => {
  const filtered = (author: ReturnType<typeof typed> | null) => ({
    ...DEFAULT_STATE,
    filters: { ...DEFAULT_STATE.filters, author },
  });

  it("keeps a step for another view, paper, period, year or clicked filter", () => {
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, view: "graph" })).toBe(true);
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, paper: "2609.30234" })).toBe(true);
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, year: 2017 })).toBe(true);
    expect(
      isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, period: { kind: "recent", range: "20" } }),
    ).toBe(true);
    expect(isNavigation(DEFAULT_STATE, filtered(exactly("Hao Li")))).toBe(true);
    expect(isNavigation(filtered(exactly("Hao Li")), filtered(typed("Hao Li")))).toBe(true);
  });

  it("replaces the entry for typing and sorting", () => {
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, query: "gaussian" })).toBe(false);
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, sort: "citations" })).toBe(false);
    expect(isNavigation(filtered(typed("hao")), filtered(typed("hao l")))).toBe(false);
  });
});
