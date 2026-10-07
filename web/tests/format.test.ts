import { describe, expect, it } from "vitest";
import {
  affiliationCoverage,
  citationsNote,
  countOf,
  firstVersionYear,
  formatDay,
  formatShortDay,
  gainLabel,
  loadingLine,
  seenHidden,
  subjectCode,
} from "../src/format";

describe("citationsNote", () => {
  const today = new Date("2026-10-01T12:00:00Z");

  it("gives the source and the date of the counts", () => {
    const note = citationsNote("Semantic Scholar", "2026-09-27T05:41:00+00:00", today);

    expect(note).toMatch(/^Citations on Semantic Scholar, as of /);
    expect(note).not.toMatch(/out of date/);
  });

  it("warns once the counts are older than two weeks", () => {
    expect(citationsNote("Semantic Scholar", "2026-09-10T05:41:00+00:00", today)).toMatch(
      / \(21 days ago: they may be out of date\)$/,
    );
  });
});

describe("affiliationCoverage", () => {
  const caveat = ": affiliations of recent years are still being filled in";

  it("gives the share of papers with known affiliations, and the caveat below half", () => {
    expect(affiliationCoverage(331, 2018)).toBe(
      `Affiliations known for 331 of ${(2018).toLocaleString()} papers (16%)${caveat}`,
    );
    expect(affiliationCoverage(1633, 3407)).toBe(
      `Affiliations known for ${(1633).toLocaleString()} of ${(3407).toLocaleString()} papers (48%)${caveat}`,
    );
    expect(affiliationCoverage(3628, 4832)).toBe(
      `Affiliations known for ${(3628).toLocaleString()} of ${(4832).toLocaleString()} papers (75%)`,
    );
  });

  it("gives no caveat at exactly half", () => {
    expect(affiliationCoverage(5, 10)).toBe("Affiliations known for 5 of 10 papers (50%)");
    expect(affiliationCoverage(4, 9)).toBe(`Affiliations known for 4 of 9 papers (44%)${caveat}`);
  });

  it("never rounds a few to 0% nor nearly all to 100%", () => {
    expect(affiliationCoverage(0, 3)).toBe(`Affiliations known for 0 of 3 papers (0%)${caveat}`);
    expect(affiliationCoverage(1, 1000)).toMatch(/ \(<1%\): /);
    expect(affiliationCoverage(999, 1000)).toMatch(/ \(>99%\)$/);
    expect(affiliationCoverage(1, 1)).toBe("Affiliations known for 1 of 1 paper (100%)");
  });

  it("names the papers counted, and gives no share of none", () => {
    expect(affiliationCoverage(2, 3, "matching paper")).toBe(
      "Affiliations known for 2 of 3 matching papers (67%)",
    );
    expect(affiliationCoverage(0, 0)).toBe("Affiliations known for 0 of 0 papers");
  });
});

describe("countOf", () => {
  it("gives a count with its noun, singular for one", () => {
    expect(countOf(0, "paper")).toBe("0 papers");
    expect(countOf(1, "paper")).toBe("1 paper");
    expect(countOf(2, "cs.CV paper")).toBe("2 cs.CV papers");
    expect(countOf(10_000, "paper")).toBe(`${(10_000).toLocaleString()} papers`);
    expect(countOf(2, "person", "people")).toBe("2 people");
    expect(countOf(1, "person", "people")).toBe("1 person");
  });
});

describe("loadingLine", () => {
  it("counts the papers of the days a period loads", () => {
    const days = [
      { date: "2026-09-25", count: 2143 },
      { date: "2026-09-24", count: 1503 },
    ];
    expect(loadingLine({ days })).toBe(`Loading ${(3646).toLocaleString()} papers of 2 days…`);
    expect(loadingLine({ days: days.slice(1) })).toBe(
      `Loading ${(1503).toLocaleString()} papers of ${formatDay("2026-09-24")}…`,
    );
    expect(loadingLine({ days: [{ date: "2026-09-26", count: 1 }] })).toMatch(
      /^Loading 1 paper of .+2026…$/,
    );
  });

  it("counts the highly cited papers of the archive's years, all of them downloaded", () => {
    expect(loadingLine({ years: [{ year: 2024, count: 3407 }] })).toBe(
      `Loading ${(3407).toLocaleString()} highly cited papers of 2024…`,
    );
    const years = [
      { year: 2025, count: 12_000 },
      { year: 2024, count: 3407 },
      { year: 2023, count: 6762 },
    ];
    expect(loadingLine({ years })).toBe(
      `Loading ${(22_169).toLocaleString()} highly cited papers of 3 years…`,
    );
  });

  it("says only that papers load while there is nothing to count", () => {
    expect(loadingLine({ days: [] })).toBe("Loading papers…");
    expect(loadingLine({ years: [] })).toBe("Loading papers…");
  });
});

describe("seenHidden", () => {
  it("counts the papers Hide seen leaves out, and says why a list is empty", () => {
    expect(seenHidden(1)).toEqual({
      count: "1 seen paper hidden",
      empty: "The only paper here is marked seen.",
    });
    expect(seenHidden(12)).toEqual({
      count: "12 seen papers hidden",
      empty: "All 12 papers here are marked seen.",
    });
  });
});

describe("gainLabel", () => {
  it("says this week for a weekly refresh, the day for a longer span", () => {
    const week = { since: "2026-10-04T05:41:00+00:00", to: "2026-10-11T06:02:00+00:00" };
    const label = gainLabel(1200, week, "Semantic Scholar");
    expect(label.text).toBe(`+${(1200).toLocaleString()} this week`);
    expect(label.title).toMatch(/^1.200 new citations on Semantic Scholar between .+ and .+$/);

    const longer = { since: "2026-09-30T13:19:35+00:00", to: "2026-10-11T06:02:00+00:00" };
    expect(gainLabel(1, longer, null).text).toMatch(/^\+1 since .*2026$/);
    expect(gainLabel(1, longer, null).title).toMatch(/^1 new citation between /);
  });
});

describe("day and subject formats", () => {
  it("formats days and subject codes", () => {
    expect(formatDay("2026-09-25")).toMatch(/2026/);
    expect(formatDay("2026-09-25T06:17:00Z")).toMatch(/2026/);
    expect(formatShortDay("2026-09-25")).toMatch(/25/);
    expect(subjectCode("Robotics (cs.RO)")).toBe("cs.RO");
    expect(subjectCode("Robotics")).toBe("Robotics");
  });
});

describe("firstVersionYear", () => {
  it("gives the year of a first version 12 months or more before the announcement", () => {
    // A paper of 2019 cross-listed in 2026.
    expect(firstVersionYear("1906.01234", "2026-09-16")).toBe(2019);
    // Exactly 12 months, whatever the day of the month.
    expect(firstVersionYear("2509.01234", "2026-09-01")).toBe(2025);
    expect(firstVersionYear("2512.01234", "2026-12-31")).toBe(2025);
    // Four-digit numbers, from before 2015.
    expect(firstVersionYear("0704.0001", "2026-09-16")).toBe(2007);
  });

  it("says nothing of a younger paper", () => {
    expect(firstVersionYear("2609.00004", "2026-09-24")).toBeNull();
    expect(firstVersionYear("2510.01234", "2026-09-30")).toBeNull();
    // Announced the month after its submission, over a new year.
    expect(firstVersionYear("2512.01234", "2026-01-02")).toBeNull();
  });

  it("does not read old-style or malformed identifiers", () => {
    expect(firstVersionYear("cs/0601001", "2026-09-16")).toBeNull();
    expect(firstVersionYear("math.GT/0309136", "2026-09-16")).toBeNull();
    expect(firstVersionYear("1913.01234", "2026-09-16")).toBeNull();
    expect(firstVersionYear("1900.01234", "2026-09-16")).toBeNull();
    expect(firstVersionYear("1906.01234", "September 2026")).toBeNull();
  });
});
