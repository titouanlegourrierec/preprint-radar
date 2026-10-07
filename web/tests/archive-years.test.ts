import { describe, expect, it } from "vitest";
import {
  ALL_YEARS,
  bestRanked,
  citationRate,
  formatYears,
  oneYear,
  parseYears,
  publishedIn,
  shownYears,
  yearsIn,
  yearsLabel,
} from "../src/archive-years";
import { makePaper } from "./fixtures";

const years = [2025, 2024, 2023, 2017].map((year) => ({ year, count: year - 2000 }));

describe("year ranges", () => {
  it("read and write the URL's forms", () => {
    expect(parseYears("2017")).toEqual(oneYear(2017));
    expect(parseYears("2021-2019")).toEqual({ from: 2019, to: 2021 });
    expect(parseYears("all")).toEqual(ALL_YEARS);
    expect(parseYears("soon")).toBeNull();
    expect(parseYears(null)).toBeNull();
    expect(formatYears(oneYear(2017))).toBe("2017");
    expect(formatYears({ from: 2019, to: 2021 })).toBe("2019-2021");
    expect(formatYears(ALL_YEARS)).toBe("all");
  });

  it("pick the archive's years within them", () => {
    expect(yearsIn({ from: 2018, to: 2024 }, years).map(({ year }) => year)).toEqual([2024, 2023]);
    expect(yearsIn(ALL_YEARS, years)).toHaveLength(4);
  });

  it("show the latest year when the URL asks none, or none of the archive's", () => {
    expect(shownYears(null, years)).toEqual(oneYear(2025));
    expect(shownYears(oneYear(2010), years)).toEqual(oneYear(2025));
    expect(shownYears({ from: 2016, to: 2018 }, years)).toEqual({ from: 2016, to: 2018 });
    expect(shownYears(ALL_YEARS, [])).toBeNull();
  });

  it("say which years they are", () => {
    expect(yearsLabel(ALL_YEARS, years)).toBe("all years");
    expect(yearsLabel({ from: 2016, to: 2024 }, years)).toBe("2017–2024");
    expect(yearsLabel(oneYear(2023), years)).toBe("2023");
    expect(publishedIn(oneYear(2023), years, undefined)).toBe("in 2023");
    expect(publishedIn(ALL_YEARS, years, undefined)).toBe("from 2017 to 2025");
    expect(publishedIn(oneYear(2025), years, new Date(2026, 9, 7))).toMatch(/^in 2025, /);
    expect(publishedIn(oneYear(2010), years, undefined)).toBe("");
  });
});

describe("bestRanked", () => {
  const asOf = new Date("2026-10-04T00:00:00Z");

  it("scores citations per year of age, a year at least", () => {
    expect(citationRate(100, "2016-10-04", asOf)).toBeCloseTo(10, 1);
    expect(citationRate(100, "2026-06-01", asOf)).toBe(100);
    expect(citationRate(undefined, "2016-10-04", asOf)).toBe(0);
  });

  it("keeps the best within the budget, all of them when they fit", () => {
    const papers = [
      makePaper({ arxiv_id: "old", announced: "2016-10-04" }),
      makePaper({ arxiv_id: "young", announced: "2024-10-04" }),
      makePaper({ arxiv_id: "unknown", announced: "2024-10-04" }),
    ];
    const counts = new Map([
      ["old", 1000],
      ["young", 400],
    ]);
    expect(bestRanked(papers, counts, asOf, 3)).toHaveLength(3);
    expect(bestRanked(papers, counts, asOf, 2).map(({ arxiv_id }) => arxiv_id)).toEqual([
      "young",
      "old",
    ]);
  });
});
