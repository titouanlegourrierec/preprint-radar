import { describe, expect, it } from "vitest";
import type { CodeFile, ScholarFile } from "../src/types";
import type { CountriesFile } from "../src/world";
import { paperFiles, withSiteFields } from "../tooling/scholar";

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

describe("withSiteFields", () => {
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
    const merged = JSON.parse(withSiteFields(JSON.stringify(day), scholar));
    expect(merged.papers).toEqual([
      { arxiv_id: "2112.00001", venue: "CVPR 2022", doi: "10.1109/CVPR52688.2022.01234" },
      { arxiv_id: "2609.00002", venue: "ICIP 2026" },
      { arxiv_id: "2609.00003" },
      { arxiv_id: "2609.00004", venue: null },
      // The authors' ids, when they are as many as the paper's authors.
      { arxiv_id: "2609.00005", authors: ["Ada", "Bob"], author_ids: ["8", null] },
    ]);
    expect(withSiteFields("unchanged", null)).toBe("unchanged");
  });

  it("adds the stars of the code, where its link is still the card's (PROD-18)", () => {
    const code: CodeFile = {
      schema_version: 1,
      category: "cs.CV",
      generated_at: "2026-10-11T06:00:00+00:00",
      since: "2026-10-04T06:00:00+00:00",
      source: "GitHub, Hugging Face",
      papers: {
        "2609.00001": { url: "https://github.com/lab/fast-net", stars: 120, gained: 4 },
        "2609.00002": { url: "https://github.com/lab/old-net", stars: 9 },
        "2609.00003": { url: "https://huggingface.co/lab/model", likes: 2 },
      },
    };
    const day = {
      papers: [
        { arxiv_id: "2609.00001", abstract: "Code: https://github.com/lab/fast-net." },
        // A new version links other code: last week's stars are not its.
        { arxiv_id: "2609.00002", abstract: "Code: https://github.com/lab/new-net" },
        { arxiv_id: "2609.00003", abstract: null, comments: "https://huggingface.co/lab/model" },
        { arxiv_id: "2609.00004", abstract: "No code." },
      ],
    };
    const merged = JSON.parse(withSiteFields(JSON.stringify(day), null, code));
    expect(merged.papers.map((paper: { code?: unknown }) => paper.code)).toEqual([
      { stars: 120, gained: 4 },
      undefined,
      { likes: 2 },
      undefined,
    ]);
  });

  it("adds the countries of the institutions with an id that OpenAlex places (PROD-22)", () => {
    const countries: CountriesFile = {
      schema_version: 1,
      generated_at: "2026-10-27T07:41:23+00:00",
      source: "OpenAlex",
      institutions: { "0abcde001": "FR", "0abcde002": "FR", "0abcde003": "US", "0abcde004": null },
    };
    const day = {
      papers: [
        { arxiv_id: "2609.00001", institution_ids: ["0abcde001", null, "0abcde002", "0abcde003"] },
        // Placed nowhere, or named by the rules without an id: no country.
        { arxiv_id: "2609.00002", institution_ids: ["0abcde004", null] },
        { arxiv_id: "2609.00003" },
      ],
    };
    const merged = JSON.parse(withSiteFields(JSON.stringify(day), null, null, countries));
    expect(merged.papers.map((paper: { countries?: string[] }) => paper.countries)).toEqual([
      ["FR", "US"],
      undefined,
      undefined,
    ]);
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
