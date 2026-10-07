import { describe, expect, it } from "vitest";
import { ALL_YEARS, oneYear } from "../src/archive-years";
import { exactly, typed } from "../src/search";
import {
  archiveYearOf,
  DEFAULT_STATE,
  isNavigation,
  paperLink,
  readState,
  writeState,
} from "../src/url-state";

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
        withCode: true,
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

  it("round-trips the graph's focus", () => {
    const state = { ...DEFAULT_STATE, view: "graph" as const, focus: "institution:mit" };
    expect(writeState(state)).toBe("?view=graph&focus=institution%3Amit");
    expect(readState(writeState(state))).toEqual(state);
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

  it("round-trips the citation sorts", () => {
    const state = { ...DEFAULT_STATE, sort: "citations" as const };
    expect(writeState(state)).toBe("?sort=citations");
    expect(readState(writeState(state))).toEqual(state);
    const rising = { ...DEFAULT_STATE, sort: "rising" as const };
    expect(readState(writeState(rising))).toEqual(rising);
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
    // "All days" left with the paper budget: its links open the longest preset.
    expect(readState("?range=all").period).toEqual({ kind: "recent", range: "40" });
    expect(readState("?from=yesterday&to=2026-13-45")).toEqual(DEFAULT_STATE);
  });
});

describe("highly cited view", () => {
  it("round-trips the view and the archive year", () => {
    const state = { ...DEFAULT_STATE, view: "cited" as const, year: oneYear(2017) };

    expect(writeState(state)).toBe("?view=cited&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips the graph of an archive year", () => {
    const state = { ...DEFAULT_STATE, view: "graph" as const, year: oneYear(2017) };

    expect(writeState(state)).toBe("?view=graph&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips the rankings of an archive year", () => {
    const state = { ...DEFAULT_STATE, view: "rankings" as const, year: oneYear(2017) };

    expect(writeState(state)).toBe("?view=rankings&year=2017");
    expect(readState(writeState(state))).toEqual(state);
  });

  it("round-trips a range of years, and all of them", () => {
    const range = { ...DEFAULT_STATE, view: "cited" as const, year: { from: 2019, to: 2021 } };
    expect(writeState(range)).toBe("?view=cited&year=2019-2021");
    expect(readState(writeState(range))).toEqual(range);
    const all = { ...DEFAULT_STATE, view: "cited" as const, year: ALL_YEARS };
    expect(writeState(all)).toBe("?view=cited&year=all");
    expect(readState(writeState(all))).toEqual(all);
  });

  it("ignores a malformed year", () => {
    expect(readState("?view=cited&year=soon").year).toBeNull();
    expect(readState("?view=cited&year=2019-20").year).toBeNull();
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
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, year: oneYear(2017) })).toBe(true);
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

describe("paperLink", () => {
  const where = { category: "cs.CV", oldestDay: "2026-09-01", archiveYears: [2017, 2025] };

  it("opens a paper of the days on its day", () => {
    expect(paperLink({ arxiv_id: "2609.30234", announced: "2026-09-25" }, where)).toBe(
      "?cat=cs.CV&from=2026-09-25&paper=2609.30234",
    );
  });

  it("opens an archived paper in its year of the Highly cited view", () => {
    const link = paperLink({ arxiv_id: "1706.03762", announced: "2017-06-12" }, where);
    expect(link).toBe("?cat=cs.CV&view=cited&paper=1706.03762&year=2017");
    expect(readState(link)).toMatchObject({
      view: "cited",
      year: oneYear(2017),
      paper: "1706.03762",
    });
  });

  it("falls back on the day when no archive year holds the paper", () => {
    expect(archiveYearOf("2019-03-01", "2026-09-01", [2017, 2025])).toBeNull();
    expect(archiveYearOf("2017-06-12", undefined, [2017])).toBeNull();
    expect(archiveYearOf("2026-09-25", "2026-09-01", [2026])).toBeNull();
  });
});
