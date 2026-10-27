import { describe, expect, it } from "vitest";
import docs from "../../docs/web.md?raw";
import { ALL_YEARS, LAST_12_MONTHS, oneYear } from "../src/archive-years";
import { exactly, NO_FILTERS, type SearchFilters, typed } from "../src/search";
import {
  archiveRangeOf,
  DEFAULT_STATE,
  isNavigation,
  isTypedChange,
  listKey,
  paperLink,
  readState,
  writeState,
} from "../src/url-state";
import source from "../src/url-state.ts?raw";

describe("url state", () => {
  it("omits defaults", () => {
    expect(writeState(DEFAULT_STATE)).toBe("");
  });

  it("round-trips a full state", () => {
    const state = {
      ...DEFAULT_STATE,
      query: 'gaussian "novel view"',
      category: "cs.CV",
      period: { kind: "recent" as const, range: "month" as const },
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

  it("round-trips the days since a day, which dates override (PROD-13)", () => {
    const state = { ...DEFAULT_STATE, period: { kind: "since" as const, from: "2026-09-15" } };
    expect(writeState(state)).toBe("?since=2026-09-15");
    expect(readState(writeState(state))).toEqual(state);
    expect(readState("?since=2026-09-15&from=2026-09-20").period).toEqual({
      kind: "dates",
      from: "2026-09-20",
      to: "2026-09-20",
    });
    expect(readState("?since=15-09-2026").period).toEqual(DEFAULT_STATE.period);
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
    const stars = { ...DEFAULT_STATE, sort: "stars" as const };
    expect(writeState(stars)).toBe("?sort=stars");
    expect(readState(writeState(stars))).toEqual(stars);
    const risingStars = { ...DEFAULT_STATE, sort: "rising-stars" as const };
    expect(writeState(risingStars)).toBe("?sort=rising-stars");
    expect(readState(writeState(risingStars))).toEqual(risingStars);
  });

  it("round-trips what Rankings ranks, and by what (SRCH-13)", () => {
    const state = { ...DEFAULT_STATE, view: "rankings" as const, rank: "author" as const };
    expect(writeState(state)).toBe("?view=rankings&rank=author");
    expect(readState(writeState(state))).toEqual(state);
    const cited = { ...state, metric: "citations" as const };
    expect(writeState(cited)).toBe("?view=rankings&rank=author&metric=citations");
    expect(readState(writeState(cited))).toEqual(cited);
    // Countries, on the world map, by their own metrics (UX-41).
    const map = { ...DEFAULT_STATE, view: "rankings" as const, rank: "country" as const };
    expect(readState(writeState({ ...map, metric: "per-million" }))).toEqual({
      ...map,
      metric: "per-million",
    });
    expect(readState("?rank=people&metric=stars")).toMatchObject({
      rank: "institution",
      metric: null,
    });
  });

  it("round-trips the reading list's folder, in its own links only (UX-38)", () => {
    const state = { ...DEFAULT_STATE, view: "reading-list" as const, folder: "To read" };
    expect(writeState(state)).toBe("?view=reading-list&folder=To+read");
    expect(readState(writeState(state))).toEqual(state);
    expect(writeState({ ...state, view: "papers" })).toBe("");
  });

  it("round-trips the Trends view's window and topic, in its own links only (PROD-20)", () => {
    const state = {
      ...DEFAULT_STATE,
      view: "trends" as const,
      window: "year" as const,
      topic: "world model",
    };
    expect(writeState(state)).toBe("?view=trends&window=year&topic=world+model");
    expect(readState(writeState(state))).toEqual(state);
    expect(writeState({ ...state, view: "papers" })).toBe("");
    expect(readState("?view=trends&window=decade").window).toBe("quarter");
  });

  it("round-trips a search of every stored paper, in the Papers view's links only (PROD-21)", () => {
    const state = { ...DEFAULT_STATE, query: "gaussian", scope: "all" as const };
    expect(writeState(state)).toBe("?q=gaussian&scope=all");
    expect(readState(writeState(state))).toEqual(state);
    expect(writeState({ ...state, view: "graph" })).toBe("?q=gaussian&view=graph");
    expect(readState("?scope=everything").scope).toBeNull();
    // Another view or source of papers, unlike typing.
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, scope: "all" })).toBe(true);
  });

  it("round-trips the topics the explorer compares, five at most (PROD-20)", () => {
    const state = { ...DEFAULT_STATE, view: "trends" as const, compare: ["mamba", "world model"] };
    expect(writeState(state)).toBe("?view=trends&compare=mamba%2Cworld+model");
    expect(readState(writeState(state))).toEqual(state);
    expect(writeState({ ...state, view: "papers" })).toBe("");
    expect(readState("?view=trends&compare=a,b,,a,c,d,e,f").compare).toEqual([
      "a",
      "b",
      "c",
      "d",
      "e",
    ]);
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
    expect(readState("?range=all").period).toEqual({ kind: "recent", range: "month" });
    // The presets of former links, counted in announcement days (SRCH-14).
    expect(readState("?range=5").period).toEqual({ kind: "recent", range: "week" });
    expect(readState("?range=20").period).toEqual({ kind: "recent", range: "month" });
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
    const recent = { ...DEFAULT_STATE, view: "cited" as const, year: LAST_12_MONTHS };
    expect(writeState(recent)).toBe("?view=cited&year=last-12-months");
    expect(readState(writeState(recent))).toEqual(recent);
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
      isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, period: { kind: "recent", range: "month" } }),
    ).toBe(true);
    expect(isNavigation(DEFAULT_STATE, filtered(exactly("Hao Li")))).toBe(true);
    expect(isNavigation(filtered(exactly("Hao Li")), filtered(typed("Hao Li")))).toBe(true);
  });

  it("replaces the entry for typing and sorting", () => {
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, query: "gaussian" })).toBe(false);
    expect(isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, sort: "citations" })).toBe(false);
    expect(isNavigation(filtered(typed("hao")), filtered(typed("hao l")))).toBe(false);
    expect(
      isNavigation(DEFAULT_STATE, { ...DEFAULT_STATE, rank: "author", metric: "papers" }),
    ).toBe(false);
    // The periods Trends compares are its order; a topic opened is a step (PROD-20).
    const trends = { ...DEFAULT_STATE, view: "trends" as const };
    expect(isNavigation(trends, { ...trends, window: "year" })).toBe(false);
    expect(isNavigation(trends, { ...trends, compare: ["mamba"] })).toBe(false);
    expect(isNavigation(trends, { ...trends, topic: "world model" })).toBe(true);
  });
});

describe("isTypedChange", () => {
  const filters = (patch: Partial<SearchFilters>): SearchFilters => ({ ...NO_FILTERS, ...patch });

  it("waits for a pause when only the typed author or affiliation text changes", () => {
    expect(isTypedChange(NO_FILTERS, filters({ author: typed("k") }))).toBe(true);
    expect(isTypedChange(filters({ author: typed("k") }), filters({ author: typed("ka") }))).toBe(
      true,
    );
    expect(
      isTypedChange(filters({ affiliation: typed("MI") }), filters({ affiliation: typed("MIT") })),
    ).toBe(true);
    // An edited clicked name stays applied until the pause.
    expect(
      isTypedChange(filters({ author: exactly("Kaiming He") }), filters({ author: typed("Kaim") })),
    ).toBe(true);
    // Other filters set before are kept as they are.
    expect(
      isTypedChange(
        filters({ withCode: true, venue: "ECCV*", author: exactly("Kaiming He") }),
        filters({
          withCode: true,
          venue: "ECCV*",
          author: exactly("Kaiming He"),
          affiliation: typed("M"),
        }),
      ),
    ).toBe(true);
  });

  it("applies at once a name clicked, a filter cleared, any other filter, or no change", () => {
    const typing = filters({ author: typed("kai") });
    expect(isTypedChange(typing, filters({ author: exactly("Kaiming He") }))).toBe(false);
    expect(isTypedChange(typing, NO_FILTERS)).toBe(false);
    expect(isTypedChange(typing, filters({ author: typed("kai") }))).toBe(false);
    expect(isTypedChange(typing, { ...typing, withCode: true })).toBe(false);
    expect(isTypedChange(typing, { ...typing, excludeCrossLists: true })).toBe(false);
    expect(isTypedChange(typing, { ...typing, venue: "ECCV 2026" })).toBe(false);
    expect(isTypedChange(typing, { ...typing, subject: "Robotics (cs.RO)" })).toBe(false);
    // Typed text with another filter in the same change (a link, Back) applies with it.
    expect(isTypedChange(typing, filters({ author: typed("kaim"), withCode: true }))).toBe(false);
    expect(
      isTypedChange(typing, filters({ author: typed("kaim"), affiliation: exactly("MIT") })),
    ).toBe(false);
  });
});

describe("paperLink", () => {
  const where = {
    category: "cs.CV",
    oldestDay: "2026-09-01",
    archiveYears: [2017, 2025],
    recentSince: "2025-10-05",
  };

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

  it("opens a paper of the last 12 months that no day file holds among the most cited", () => {
    // Its year, 2025, is the archive's too: the papers of its first 9 months.
    const link = paperLink({ arxiv_id: "2511.21631", announced: "2025-11-27" }, where);
    expect(link).toBe("?cat=cs.CV&view=cited&paper=2511.21631&year=last-12-months");
    expect(archiveRangeOf("2025-10-05", where)).toBe(LAST_12_MONTHS);
    expect(archiveRangeOf("2025-10-04", where)).toEqual(oneYear(2025));
    // Before the archive keeps them, in their year.
    expect(archiveRangeOf("2025-11-27", { ...where, recentSince: undefined })).toEqual(
      oneYear(2025),
    );
  });

  it("falls back on the day when no archive year holds the paper", () => {
    const before = { oldestDay: "2026-09-01", archiveYears: [2017, 2025], recentSince: undefined };
    expect(archiveRangeOf("2019-03-01", before)).toBeNull();
    expect(archiveRangeOf("2017-06-12", { ...before, oldestDay: undefined })).toBeNull();
    expect(archiveRangeOf("2026-09-25", { ...where, archiveYears: [2026] })).toBeNull();
  });
});

describe("listKey", () => {
  it("changes with what makes a new list, not with a shared paper or the graph's focus", () => {
    const base = listKey(DEFAULT_STATE, "");
    expect(listKey({ ...DEFAULT_STATE, paper: "2609.30234", focus: "institution:mit" }, "")).toBe(
      base,
    );
    expect(listKey({ ...DEFAULT_STATE, period: { ...DEFAULT_STATE.period } }, "")).toBe(base);
    expect(listKey(DEFAULT_STATE, "gaussian")).not.toBe(base);
    expect(listKey({ ...DEFAULT_STATE, sort: "citations" }, "")).not.toBe(base);
    expect(listKey({ ...DEFAULT_STATE, view: "cited" }, "")).not.toBe(base);
    expect(
      listKey({ ...DEFAULT_STATE, filters: { ...DEFAULT_STATE.filters, withCode: true } }, ""),
    ).not.toBe(base);
  });
});

describe("the URL's parameters", () => {
  it("are all documented in docs/web.md", () => {
    const read = new Set([
      ...[...source.matchAll(/params\.get\("(\w+)"\)/g)].map((match) => match[1]),
      ...[...source.matchAll(/readName\(params, "(\w+)", "(\w+)"\)/g)].flatMap((match) => [
        match[1],
        match[2],
      ]),
    ]);
    expect(read.size).toBeGreaterThan(15);
    for (const name of read) expect(docs).toContain(`\`${name}\``);
  });
});
