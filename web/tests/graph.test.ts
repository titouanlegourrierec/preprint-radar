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
  papers: false,
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

describe("buildGraph with author affiliations", () => {
  const mapped = makePaper({
    arxiv_id: "9",
    authors: ["Ada", "Bob"],
    affiliations: ["MIT", "ETH Zurich"],
    author_affiliations: [[0], null],
  });

  it("links a placed author only to their own institutions", () => {
    const graph = buildGraph([mapped], { ...INSTITUTIONS, authors: true });
    const links = graph.links.map(({ source, target }) => `${source}->${target}`).sort();

    expect(links).toEqual([
      "author:ada->author:bob",
      "author:ada->institution:mit",
      "author:bob->institution:eth zurich",
      "author:bob->institution:mit",
      "institution:eth zurich->institution:mit",
    ]);
  });

  it("drops the author-institution edge when their institution is filtered out", () => {
    const twice = makePaper({ arxiv_id: "10", authors: ["Cyd"], affiliations: ["MIT"] });
    const graph = buildGraph([mapped, twice], {
      ...INSTITUTIONS,
      authors: true,
      minPapers: { institution: 2, author: 1 },
    });

    // Only MIT survives; Ada, mapped to it, keeps no edge to ETH Zurich; Bob falls back.
    expect(graph.links.map(({ source, target }) => `${source}->${target}`).sort()).toEqual([
      "author:ada->author:bob",
      "author:ada->institution:mit",
      "author:bob->institution:mit",
      "author:cyd->institution:mit",
    ]);
  });
});

describe("buildGraph with papers", () => {
  const mapped = makePaper({
    arxiv_id: "9",
    title: "Gaussian Splatting for Everyone",
    authors: ["Ada", "Bob"],
    affiliations: ["MIT", "ETH Zurich"],
    author_affiliations: [[0], null],
  });
  const PAPERS: GraphOptions = { ...INSTITUTIONS, papers: true };
  const edges = (graph: ReturnType<typeof buildGraph>) =>
    graph.links.map(({ source, target }) => `${source}->${target}`).sort();

  it("links each paper to its institutions when authors are hidden", () => {
    const graph = buildGraph(papers, PAPERS);

    expect(graph.nodes.map((node) => node.id)).toEqual([
      "institution:google",
      "institution:mit",
      "institution:kaist",
      "paper:1",
      "paper:2",
      "paper:3",
    ]);
    expect(edges(graph)).toEqual([
      "institution:google->paper:1",
      "institution:google->paper:2",
      "institution:kaist->paper:3",
      "institution:mit->paper:1",
      "institution:mit->paper:2",
    ]);
  });

  it("hangs institutions from the authors placed there, else from the paper", () => {
    const graph = buildGraph([mapped], { ...PAPERS, authors: true });

    // Ada is placed at MIT; nobody shown is placed at ETH, and Bob is not placed at all.
    expect(edges(graph)).toEqual([
      "author:ada->institution:mit",
      "author:ada->paper:9",
      "author:bob->paper:9",
      "institution:eth zurich->paper:9",
    ]);
  });

  it("falls back to the paper when the placed author is filtered out", () => {
    const graph = buildGraph([mapped], {
      ...PAPERS,
      authors: true,
      minPapers: { institution: 1, author: 2 },
    });

    expect(edges(graph)).toEqual(["institution:eth zurich->paper:9", "institution:mit->paper:9"]);
  });

  it("links papers to authors only when institutions are hidden", () => {
    const graph = buildGraph(papers, { ...PAPERS, institutions: false, authors: true });

    expect(edges(graph)).toEqual([
      "author:ada->paper:1",
      "author:ada->paper:2",
      "author:bob->paper:1",
      "author:cyd->paper:3",
    ]);
  });

  it("drops papers left without any link unless isolated nodes are kept", () => {
    const bare = makePaper({ arxiv_id: "11", affiliations: null });

    expect(buildGraph([bare], { ...PAPERS, isolated: false }).nodes).toEqual([]);
    expect(buildGraph([bare], PAPERS).nodes.map((node) => node.id)).toEqual(["paper:11"]);
  });

  it("finds papers by their title", () => {
    const [node] = buildGraph([mapped], { ...PAPERS, institutions: false }).nodes;

    expect(node && nodeMatches(node, searchKey("splatting"))).toBe(true);
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
