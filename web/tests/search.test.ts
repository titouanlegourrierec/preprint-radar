import { describe, expect, it } from "vitest";
import { facetCounts, NO_FILTERS, PaperIndex, parseQuery } from "../src/search";
import { makePaper } from "./fixtures";

const papers = [
  makePaper({
    arxiv_id: "2609.00001",
    announced: "2026-09-24",
    title: "Practical Compression of 3D Gaussian Splatting",
    abstract: "We compress Gaussian splats for novel view synthesis.",
    authors: ["Tomás Lozano-Pérez", "Jane Doe"],
    affiliations: ["MIT", "NVIDIA"],
  }),
  makePaper({
    arxiv_id: "2609.00002",
    title: "Diffusion Models for Video Generation",
    abstract: "A survey of video diffusion models.",
    affiliations: ["MIT"],
    cross_list_from: "cs.LG",
    primary_subject: "Machine Learning (cs.LG)",
  }),
  makePaper({
    arxiv_id: "2609.00003",
    title: "Robot Grasping with Vision",
    abstract: "Grasping objects using novel view synthesis priors.",
    affiliations: [],
  }),
];

const index = new PaperIndex(papers);
const ids = (query: string, filters = NO_FILTERS) =>
  index.search(query, filters, "relevance").map(({ paper }) => paper.arxiv_id);

describe("parseQuery", () => {
  it("separates phrases, exclusions and free text", () => {
    expect(parseQuery('gaussian "Novel View" -survey  splats')).toEqual({
      text: "gaussian splats",
      phrases: ["novel view"],
      excluded: ["survey"],
    });
  });
});

describe("PaperIndex", () => {
  it("returns everything, newest first, without a query", () => {
    expect(ids("")).toEqual(["2609.00003", "2609.00002", "2609.00001"]);
  });

  it("requires all terms and supports prefixes", () => {
    expect(ids("gauss compress")).toEqual(["2609.00001"]);
  });

  it("ignores stop words and tolerates typos", () => {
    expect(ids("difusion for video")).toEqual(["2609.00002"]);
  });

  it("matches authors without accents", () => {
    expect(ids("perez")).toEqual(["2609.00001"]);
  });

  it("supports phrases and exclusions", () => {
    expect(ids('"novel view synthesis"').sort()).toEqual(["2609.00001", "2609.00003"]);
    expect(ids('"novel view synthesis" -grasping')).toEqual(["2609.00001"]);
  });

  it("applies structured filters", () => {
    expect(ids("", { ...NO_FILTERS, excludeCrossLists: true })).not.toContain("2609.00002");
    expect(ids("", { ...NO_FILTERS, affiliation: "NVIDIA" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, author: "Jane Doe" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, subject: "Machine Learning (cs.LG)" })).toEqual(["2609.00002"]);
  });

  it("reports matched terms for highlighting", () => {
    const [result] = index.search("splatting", NO_FILTERS, "relevance");
    expect(result?.highlights).toContain("splatting");
  });

  it("deduplicates papers present in several days", () => {
    expect(new PaperIndex([...papers, ...papers]).size).toBe(3);
  });
});

describe("facetCounts", () => {
  it("counts values across results, most frequent first", () => {
    const results = index.search("", NO_FILTERS, "newest");
    expect(facetCounts(results, (paper) => paper.affiliations ?? [], 5)).toEqual([
      { value: "MIT", count: 2 },
      { value: "NVIDIA", count: 1 },
    ]);
  });
});
