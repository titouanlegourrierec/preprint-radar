import { describe, expect, it } from "vitest";
import {
  ANY_VENUE,
  alphabetical,
  facetCounts,
  NO_FILTERS,
  PaperIndex,
  parseQuery,
} from "../src/search";
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
    venue: "NeurIPS 2026",
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

  it("searches venues", () => {
    expect(ids("neurips")).toEqual(["2609.00002"]);
  });

  it("applies structured filters", () => {
    expect(ids("", { ...NO_FILTERS, excludeCrossLists: true })).not.toContain("2609.00002");
    expect(ids("", { ...NO_FILTERS, affiliation: "NVIDIA" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, author: "Jane Doe" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, subject: "Machine Learning (cs.LG)" })).toEqual(["2609.00002"]);
  });

  it("filters by venue, or keeps every paper accepted somewhere", () => {
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS 2026" })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: ANY_VENUE })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS" })).toEqual([]);
  });

  it("matches author and affiliation filters by substring, ignoring case and accents", () => {
    expect(ids("", { ...NO_FILTERS, affiliation: "nvid" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, affiliation: "mit" }).sort()).toEqual([
      "2609.00001",
      "2609.00002",
    ]);
    expect(ids("", { ...NO_FILTERS, author: "perez" })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, author: "  " })).toHaveLength(3);
  });

  it("finds affiliations by the name of their institution", () => {
    const named = new PaperIndex([
      makePaper({
        arxiv_id: "2609.00010",
        affiliations: ["University of Padova, Italy"],
        institutions: ["University of Padua"],
      }),
    ]);
    const find = (query: string, affiliation: string | null = null) =>
      named.search(query, { ...NO_FILTERS, affiliation }, "relevance").length;

    // "MIT" is named Massachusetts Institute of Technology, as in the graph.
    expect(ids("", { ...NO_FILTERS, affiliation: "Massachusetts Institute" }).sort()).toEqual([
      "2609.00001",
      "2609.00002",
    ]);
    expect(find("", "University of Padua")).toBe(1);
    expect(find("padua")).toBe(1);
  });

  it("does not highlight stop words of filters", () => {
    const tokyo = new PaperIndex([
      makePaper({ arxiv_id: "1", affiliations: ["University of Tokyo"] }),
    ]);
    const [result] = tokyo.search(
      "",
      { ...NO_FILTERS, affiliation: "University of Tokyo" },
      "newest",
    );
    expect(result?.highlights).toEqual(["university", "tokyo"]);
  });

  it("highlights the text of author and affiliation filters", () => {
    const [result] = index.search("", { ...NO_FILTERS, affiliation: "nvidia" }, "newest");
    expect(result?.highlights).toContain("nvidia");
  });

  it("reports matched terms for highlighting", () => {
    const [result] = index.search("splatting", NO_FILTERS, "relevance");
    expect(result?.highlights).toContain("splatting");
  });

  it("deduplicates papers present in several days", () => {
    expect(new PaperIndex([...papers, ...papers]).size).toBe(3);
  });
});

describe("alphabetical", () => {
  it("sorts values ignoring case and accents", () => {
    const sorted = alphabetical([
      { value: "Zhejiang University", count: 9 },
      { value: "École Polytechnique", count: 1 },
      { value: "adobe", count: 2 },
      { value: "ETH Zurich", count: 5 },
    ]).map(({ value }) => value);

    expect(sorted).toEqual(["adobe", "École Polytechnique", "ETH Zurich", "Zhejiang University"]);
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
