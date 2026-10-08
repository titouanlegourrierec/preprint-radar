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
    "2609.00005": { author_ids: ["8", null] },
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
        { arxiv_id: "2609.00005", authors: ["Ada", "Bob"] },
      ],
    };
    const merged = JSON.parse(withScholar(JSON.stringify(day), scholar));
    expect(merged.papers).toEqual([
      { arxiv_id: "2112.00001", venue: "CVPR 2022", doi: "10.1109/CVPR52688.2022.01234" },
      { arxiv_id: "2609.00002", venue: "ICIP 2026" },
      { arxiv_id: "2609.00003" },
      { arxiv_id: "2609.00004", venue: null },
      // The authors' ids, when they are as many as the paper's authors.
      { arxiv_id: "2609.00005", authors: ["Ada", "Bob"], author_ids: ["8", null] },
    ]);
    expect(withScholar("unchanged", null)).toBe("unchanged");
  });

  it("lists the day and archive files of the index, and the most cited of the last 12 months", () => {
    expect(
      paperFiles({
        categories: { "cs.CV": [{ date: "2026-09-25" }], "cs.RO": [] },
        archives: { "cs.CV": [{ year: 2017 }] },
        top_recent: { "cs.CV": { since: "2025-10-05", count: 1 } },
      }),
    ).toEqual([
      { category: "cs.CV", path: "cs.CV/2026-09-25.json" },
      { category: "cs.CV", path: "cs.CV/archive/2017.json" },
      { category: "cs.CV", path: "cs.CV/top-recent.json" },
    ]);
    expect(paperFiles({ categories: { "cs.CV": [] } })).toEqual([]);
  });
});
