import { describe, expect, it } from "vitest";
import {
  buildGraph,
  type GraphOptions,
  institutionName,
  nodeMatches,
  searchKey,
} from "../src/graph";
import { makePaper } from "./fixtures";

describe("institutionName", () => {
  it.each([
    ["Carnegie Mellon University, United States of America", "Carnegie Mellon University"],
    ["School of Computer Science, Peking University", "Peking University"],
    ["Google, Switzerland", "Google"],
    ["Pengcheng Laboratory, China", "Pengcheng Laboratory"],
    [
      "School of Human Settlements and Civil Engineering, Xi’an Jiaotong University, Xi’an, 710049, China",
      "Xi’an Jiaotong University",
    ],
    ["The University of Texas at Austin", "University of Texas at Austin"],
    ["KAIST", "KAIST"],
    ["Meta", "Meta"],
    ["and", ""],
  ])("%s -> %s", (affiliation, expected) => {
    expect(institutionName(affiliation)).toBe(expected);
  });
});

const papers = [
  makePaper({
    arxiv_id: "1",
    authors: ["Ada", "Bob"],
    affiliations: ["MIT, USA", "Google, Switzerland"],
  }),
  makePaper({ arxiv_id: "2", authors: ["Ada"], affiliations: ["MIT", "Google"] }),
  makePaper({ arxiv_id: "3", authors: ["Cyd"], affiliations: ["KAIST"] }),
];

const INSTITUTIONS: GraphOptions = {
  institutions: true,
  authors: false,
  minPapers: { institution: 1, author: 1 },
  isolated: true,
  maxNodes: Number.POSITIVE_INFINITY,
};

describe("buildGraph", () => {
  it("merges institution variants and links institutions sharing papers", () => {
    const graph = buildGraph(papers, INSTITUTIONS);

    expect(graph.nodes.map((node) => [node.label, node.paperIds.length])).toEqual([
      ["Google", 2],
      ["MIT", 2],
      ["KAIST", 1],
    ]);
    expect(graph.links).toEqual([
      { source: "institution:google", target: "institution:mit", weight: 2 },
    ]);
    expect(graph.truncated).toBe(false);
  });

  it("filters rare nodes and caps the node count", () => {
    const graph = buildGraph(papers, {
      ...INSTITUTIONS,
      minPapers: { institution: 2, author: 1 },
      maxNodes: 1,
    });

    expect(graph.nodes.map((node) => node.label)).toEqual(["Google"]);
    expect(graph.links).toEqual([]);
    expect(graph.truncated).toBe(true);
  });

  it("adds authors when requested, with their own threshold", () => {
    const graph = buildGraph(papers, {
      ...INSTITUTIONS,
      authors: true,
      minPapers: { institution: 2, author: 1 },
    });

    expect(graph.nodes.map((node) => node.id).sort()).toEqual([
      "author:ada",
      "author:bob",
      "author:cyd",
      "institution:google",
      "institution:mit",
    ]);
    expect(graph.links).toHaveLength(6);
  });

  it("can show authors only", () => {
    const graph = buildGraph(papers, { ...INSTITUTIONS, institutions: false, authors: true });

    expect(graph.nodes.map((node) => node.kind)).toEqual(["author", "author", "author"]);
    expect(graph.links).toEqual([{ source: "author:ada", target: "author:bob", weight: 1 }]);
  });

  it("can hide nodes that share no paper with another node", () => {
    const graph = buildGraph(papers, { ...INSTITUTIONS, isolated: false });

    expect(graph.nodes.map((node) => node.label)).toEqual(["Google", "MIT"]);
  });
});

describe("nodeMatches", () => {
  const [google] = buildGraph(papers, INSTITUTIONS).nodes;

  it("matches part of a name, ignoring case, accents and punctuation", () => {
    expect(google && nodeMatches(google, searchKey("GOOG"))).toBe(true);
    expect(searchKey("Xi’an  Jiaotong-Univ.")).toBe("xi an jiaotong univ");
  });

  it("does not match the kind prefix or an empty search", () => {
    expect(google && nodeMatches(google, searchKey("institution"))).toBe(false);
    expect(google && nodeMatches(google, "")).toBe(false);
  });
});
