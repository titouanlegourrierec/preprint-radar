import { describe, expect, it } from "vitest";
import {
  ANY_VENUE,
  familyOf,
  isMajorVenue,
  MAJOR_VENUES,
  matchesVenue,
  sortVenues,
  venueFacets,
  venueFamily,
  venueLabel,
} from "../src/venues";
import { makePaper } from "./fixtures";

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

  it("puts each family before its editions, and a workshop's after the conference's", () => {
    const sorted = sortVenues([
      venue("CVPR 2026 Workshop"),
      venue("CVPR 2026"),
      venue("CVPR Workshop*"),
      venue("CVPR 2025"),
      venue("CVPR*"),
      venue("TPAMI 2025"),
      venue("TPAMI*"),
    ]).map(({ value }) => value);

    expect(sorted).toEqual([
      "CVPR*",
      "CVPR 2025",
      "CVPR 2026",
      "CVPR Workshop*",
      "CVPR 2026 Workshop",
      "TPAMI*",
      "TPAMI 2025",
    ]);
  });

  it("does not mistake a longer acronym for a major venue", () => {
    const sorted = sortVenues([venue("ICMLA 2026"), venue("ICML 2026")]).map(({ value }) => value);

    expect(sorted).toEqual(["ICML 2026", "ICMLA 2026"]);
  });

  it("recognizes major venues by name, year or workshop", () => {
    expect(isMajorVenue("NeurIPS 2026 Workshop")).toBe(true);
    expect(isMajorVenue("MICCAI")).toBe(true);
    expect(isMajorVenue("CVPR*")).toBe(true);
    expect(isMajorVenue("CVPR Workshop*")).toBe(true);
    expect(isMajorVenue("ICMLA 2026")).toBe(false);
    expect(isMajorVenue("BMVC 2026")).toBe(false);
  });

  it("lists every major venue", () => {
    expect(MAJOR_VENUES).toContain("NeurIPS");
    expect(MAJOR_VENUES).toContain("MICCAI");
  });
});

describe("venue families", () => {
  it("are a venue without its year, a workshop apart", () => {
    expect(venueFamily("CVPR 2026")).toBe("CVPR");
    expect(venueFamily("CVPR 2026 Workshop")).toBe("CVPR Workshop");
    expect(venueFamily("ACM MM 2026")).toBe("ACM MM");
    expect(venueFamily("Pattern Recognition 1998")).toBe("Pattern Recognition");
    expect(venueFamily("ICLR")).toBe("ICLR");
    // A year that is part of the name stays.
    expect(venueFamily("2026 IEEE Workshop on Things")).toBe("2026 IEEE Workshop on Things");
  });

  it("are a filter value of their own", () => {
    expect(familyOf("CVPR*")).toBe("CVPR");
    expect(familyOf(ANY_VENUE)).toBeNull();
    expect(familyOf("CVPR 2026")).toBeNull();
    expect(venueLabel("CVPR*")).toBe("CVPR, any year");
    expect(venueLabel(ANY_VENUE)).toBe("any venue");
    expect(venueLabel("ECCV 2026")).toBe("ECCV 2026");
  });

  it("match every edition of the venue, not its workshops", () => {
    expect(matchesVenue("CVPR 2025", "CVPR*")).toBe(true);
    expect(matchesVenue("CVPR", "CVPR*")).toBe(true);
    expect(matchesVenue("CVPR 2026 Workshop", "CVPR*")).toBe(false);
    expect(matchesVenue("CVPR 2026 Workshop", "CVPR Workshop*")).toBe(true);
    expect(matchesVenue("ICCV 2025", "CVPR*")).toBe(false);
    expect(matchesVenue("CVPR 2025", "CVPR 2025")).toBe(true);
    expect(matchesVenue("CVPR 2025", "CVPR 2026")).toBe(false);
    expect(matchesVenue("CVPR 2025", ANY_VENUE)).toBe(true);
    expect(matchesVenue(null, ANY_VENUE)).toBe(false);
    expect(matchesVenue(undefined, "CVPR*")).toBe(false);
  });

  it("are listed with the editions when there are several, counted on the papers", () => {
    const papers = [
      makePaper({ arxiv_id: "1", venue: "CVPR 2026" }),
      makePaper({ arxiv_id: "2", venue: "CVPR 2026" }),
      makePaper({ arxiv_id: "3", venue: "CVPR 2025" }),
      makePaper({ arxiv_id: "4", venue: "ECCV 2026" }),
      makePaper({ arxiv_id: "5", venue: null }),
    ];
    expect(venueFacets(papers, 10)).toEqual([
      { value: ANY_VENUE, count: 4 },
      { value: "CVPR*", count: 3 },
      { value: "CVPR 2026", count: 2 },
      { value: "CVPR 2025", count: 1 },
      { value: "ECCV 2026", count: 1 },
    ]);
    // The papers accepted anywhere are counted over all of them, past the limit too.
    expect(venueFacets(papers, 2)).toEqual([
      { value: ANY_VENUE, count: 4 },
      { value: "CVPR*", count: 3 },
      { value: "CVPR 2026", count: 2 },
    ]);
  });
});
