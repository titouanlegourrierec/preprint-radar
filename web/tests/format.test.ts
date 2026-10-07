import { describe, expect, it } from "vitest";
import {
  citationsNote,
  countOf,
  formatDay,
  formatShortDay,
  gainLabel,
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
