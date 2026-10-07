import { describe, expect, it } from "vitest";
import type { ScholarFile } from "../src/types";
import { authorIdsByName, paperFiles, withScholar } from "../tooling/scholar";

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

  it("gives the site's records their authors' ids, by name where only one person has it", () => {
    const papers = (...entries: object[]) => JSON.stringify({ schema_version: 1, papers: entries });
    const ids: ScholarFile = {
      ...scholar,
      papers: {
        "1": { author_ids: ["42", null] },
        "2": { author_ids: ["7", "9"] },
        "3": { author_ids: ["8"] },
      },
    };
    const day = papers(
      { arxiv_id: "1", authors: ["Wei Wang", "Ada Lovelace"] },
      { arxiv_id: "2", authors: ["Wei Wang", "Ada Lovelace"] },
      // One author too many: its ids are not the paper's.
      { arxiv_id: "3", authors: ["Alan Turing", "Bob"] },
      { arxiv_id: "4", authors: ["Wei Wang", "Ada Lovelace", "Cyd"] },
    );
    const byName = authorIdsByName([day], ids);

    // Two people are Wei Wang, one is Ada Lovelace; Alan Turing's id was not his.
    expect([...byName]).toEqual([["ada lovelace", "9"]]);
    const merged = JSON.parse(withScholar(day, ids, byName)).papers;
    expect(merged.map((paper: { author_ids?: unknown }) => paper.author_ids)).toEqual([
      ["42", "9"],
      ["7", "9"],
      undefined,
      [null, "9", null],
    ]);
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
