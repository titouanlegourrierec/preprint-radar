import { describe, expect, it } from "vitest";
import type { ScholarFile } from "../src/types";
import { paperFiles, withScholar } from "../tooling/scholar";

const scholar: ScholarFile = {
  schema_version: 1,
  category: "cs.CV",
  generated_at: "2026-10-04T06:00:00+00:00",
  source: "Semantic Scholar",
  papers: {
    "2112.00001": { doi: "10.1109/CVPR52688.2022.01234", venue: "CVPR 2022" },
    "2609.00002": { venue: "International Conference on Information Photonics 2026" },
    "2609.00003": { author_ids: ["1"] },
  },
};

describe("withScholar", () => {
  it("adds the DOI, and the published venue where the comments name none", () => {
    const day = {
      schema_version: 1,
      papers: [
        { arxiv_id: "2112.00001", venue: null },
        // The comments' venue wins: Semantic Scholar takes ICIP for Information Photonics.
        { arxiv_id: "2609.00002", venue: "ICIP 2026" },
        { arxiv_id: "2609.00003" },
        { arxiv_id: "2609.00004", venue: null },
      ],
    };
    const merged = JSON.parse(withScholar(JSON.stringify(day), scholar));
    expect(merged.papers).toEqual([
      { arxiv_id: "2112.00001", venue: "CVPR 2022", doi: "10.1109/CVPR52688.2022.01234" },
      { arxiv_id: "2609.00002", venue: "ICIP 2026" },
      { arxiv_id: "2609.00003" },
      { arxiv_id: "2609.00004", venue: null },
    ]);
    expect(withScholar("unchanged", null)).toBe("unchanged");
  });

  it("lists the day and archive files of the index", () => {
    expect(
      paperFiles({
        categories: { "cs.CV": [{ date: "2026-09-25" }], "cs.RO": [] },
        archives: { "cs.CV": [{ year: 2017 }] },
      }),
    ).toEqual([
      { category: "cs.CV", path: "cs.CV/2026-09-25.json" },
      { category: "cs.CV", path: "cs.CV/archive/2017.json" },
    ]);
    expect(paperFiles({ categories: { "cs.CV": [] } })).toEqual([]);
  });
});
