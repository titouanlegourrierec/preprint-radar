import { describe, expect, it } from "vitest";
import { isMajorVenue, MAJOR_VENUES, sortVenues } from "../src/venues";

const venue = (value: string, count = 1) => ({ value, count });

describe("sortVenues", () => {
  it("pins major venues in their canonical order, with their years and workshops", () => {
    const sorted = sortVenues([
      venue("ACCV 2026"),
      venue("CVPR 2026"),
      venue("NeurIPS 2026 Workshop"),
      venue("MICCAI 2026"),
      venue("NeurIPS 2026", 50),
      venue("ICLR"),
    ]).map(({ value }) => value);

    expect(sorted).toEqual([
      "NeurIPS 2026",
      "NeurIPS 2026 Workshop",
      "ICLR",
      "CVPR 2026",
      "MICCAI 2026",
      "ACCV 2026",
    ]);
  });

  it("sorts the other venues alphabetically, ignoring case", () => {
    const sorted = sortVenues([venue("WACV 2027"), venue("ACM MM 2026"), venue("BMVC 2026")]).map(
      ({ value }) => value,
    );

    expect(sorted).toEqual(["ACM MM 2026", "BMVC 2026", "WACV 2027"]);
  });

  it("does not mistake a longer acronym for a major venue", () => {
    const sorted = sortVenues([venue("ICMLA 2026"), venue("ICML 2026")]).map(({ value }) => value);

    expect(sorted).toEqual(["ICML 2026", "ICMLA 2026"]);
  });

  it("recognizes major venues by name, year or workshop", () => {
    expect(isMajorVenue("NeurIPS 2026 Workshop")).toBe(true);
    expect(isMajorVenue("MICCAI")).toBe(true);
    expect(isMajorVenue("ICMLA 2026")).toBe(false);
    expect(isMajorVenue("BMVC 2026")).toBe(false);
  });

  it("lists every major venue", () => {
    expect(MAJOR_VENUES).toContain("NeurIPS");
    expect(MAJOR_VENUES).toContain("MICCAI");
  });
});
