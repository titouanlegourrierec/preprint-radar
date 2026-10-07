import { describe, expect, it } from "vitest";
import {
  buildGraph,
  canonicalNodeId,
  countPeople,
  entitiesByPaper,
  type GraphOptions,
  linkPapers,
  MAX_CLIQUE_AUTHORS,
  MAX_REPLAY_STEPS,
  matchStatus,
  nodeConnections,
  nodeLabel,
  nodeMatches,
  papersOfNode,
  replaySteps,
  sharedPapers,
} from "../src/graph";
import { searchKey } from "../src/text";
import { makePaper } from "./fixtures";

const papers = [
  makePaper({
    arxiv_id: "1",
    authors: ["Ada", "Bob"],
    affiliations: ["Inria, France", "Google, Switzerland"],
  }),
  makePaper({ arxiv_id: "2", authors: ["Ada"], affiliations: ["Inria", "Google"] }),
  makePaper({ arxiv_id: "3", authors: ["Cyd"], affiliations: ["Tsinghua University"] }),
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
      ["Inria", 2],
      ["Tsinghua University", 1],
    ]);
    expect(graph.links).toEqual([
      { source: "institution:google", target: "institution:inria", weight: 2 },
    ]);
    expect(graph.truncated).toBe(false);
  });

  it("keeps an institution's ROR id from the papers that give it", () => {
    const named = (arxiv_id: string, ids?: (string | null)[]) =>
      makePaper({
        arxiv_id,
        affiliations: ["School of CS, Peking University", "Lab"],
        institutions: ["Peking University", null],
        ...(ids ? { institution_ids: ids } : {}),
      });
    const graph = buildGraph([named("1"), named("2", ["02v51f717", null])], INSTITUTIONS);
    const ids = Object.fromEntries(graph.nodes.map((node) => [node.label, node.rorId]));
    expect(ids).toMatchObject({ "Peking University": "02v51f717" });
    expect(graph.nodes.find((node) => node.label === "Lab")?.rorId).toBeUndefined();
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
    expect(graph.eligible).toBe(2);
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
      "institution:inria",
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

    expect(graph.nodes.map((node) => node.label)).toEqual(["Google", "Inria"]);
  });

  it("merges an author spelled with ß and with ss", () => {
    const spelled = [
      makePaper({ arxiv_id: "1", authors: ["Matthias Nießner"] }),
      makePaper({ arxiv_id: "2", authors: ["Matthias Niessner"] }),
      makePaper({ arxiv_id: "3", authors: ["Matthias Nießner"] }),
    ];
    const graph = buildGraph(spelled, { ...INSTITUTIONS, institutions: false, authors: true });

    expect(graph.nodes.map((node) => [node.id, node.label, node.paperIds.length])).toEqual([
      ["author:matthias niessner", "Matthias Nießner", 3],
    ]);
  });
});

describe("buildGraph of a consortium paper", () => {
  const consortium = makePaper({
    arxiv_id: "2407.21783",
    authors: Array.from({ length: MAX_CLIQUE_AUTHORS + 1 }, (_, index) => `Author ${index}`),
    affiliations: ["Meta"],
  });
  const small = makePaper({
    arxiv_id: "1",
    authors: ["Author 0", "Author 1"],
    affiliations: ["Meta"],
  });
  const projection: GraphOptions = { ...INSTITUTIONS, authors: true, isolated: false };

  it("does not link its authors to one another, but to its institutions", () => {
    const graph = buildGraph([consortium, small], projection);
    const pairs = graph.links.filter(
      (link) => link.source.startsWith("author:") && link.target.startsWith("author:"),
    );

    // Only the small paper's pair: the consortium adds no author-author link.
    expect(pairs).toEqual([{ source: "author:author 0", target: "author:author 1", weight: 1 }]);
    expect(graph.links.filter((link) => link.target === "institution:meta")).toHaveLength(
      MAX_CLIQUE_AUTHORS + 1,
    );
    expect(graph.consortia).toBe(1);
  });

  it("is linked like any paper when papers are shown", () => {
    const graph = buildGraph([consortium], { ...projection, papers: true });

    expect(graph.consortia).toBe(0);
    const toAuthors = graph.links.filter(
      (link) => link.target === "paper:2407.21783" && link.source.startsWith("author:"),
    );
    expect(toAuthors).toHaveLength(MAX_CLIQUE_AUTHORS + 1);
  });
});

describe("buildGraph with author affiliations", () => {
  const mapped = makePaper({
    arxiv_id: "9",
    authors: ["Ada", "Bob"],
    affiliations: ["Inria", "ETH Zurich"],
    author_affiliations: [[0], null],
  });

  it("links a placed author only to their own institutions", () => {
    const graph = buildGraph([mapped], { ...INSTITUTIONS, authors: true });
    const links = graph.links.map(({ source, target }) => `${source}->${target}`).sort();

    expect(links).toEqual([
      "author:ada->author:bob",
      "author:ada->institution:inria",
      "author:bob->institution:eth zurich",
      "author:bob->institution:inria",
      "institution:eth zurich->institution:inria",
    ]);
  });

  it("places nobody when the mapping is out of step with the authors", () => {
    const stale = makePaper({ ...mapped, authors: ["Ada", "Bob", "Cyd"] });
    const graph = buildGraph([stale], { ...INSTITUTIONS, authors: true });
    const links = graph.links.map(({ source, target }) => `${source}->${target}`);

    // Every author falls back to every institution of the paper.
    expect(links).toContain("author:ada->institution:eth zurich");
    expect(links).toContain("author:cyd->institution:inria");
  });

  it("drops the author-institution edge when their institution is filtered out", () => {
    const twice = makePaper({ arxiv_id: "10", authors: ["Cyd"], affiliations: ["Inria"] });
    const graph = buildGraph([mapped, twice], {
      ...INSTITUTIONS,
      authors: true,
      minPapers: { institution: 2, author: 1 },
    });

    // Only Inria survives; Ada, mapped to it, keeps no edge to ETH Zurich; Bob falls back.
    expect(graph.links.map(({ source, target }) => `${source}->${target}`).sort()).toEqual([
      "author:ada->author:bob",
      "author:ada->institution:inria",
      "author:bob->institution:inria",
      "author:cyd->institution:inria",
    ]);
  });
});

describe("buildGraph with papers", () => {
  const mapped = makePaper({
    arxiv_id: "9",
    title: "Gaussian Splatting for Everyone",
    authors: ["Ada", "Bob"],
    affiliations: ["Inria", "ETH Zurich"],
    author_affiliations: [[0], null],
  });
  const PAPERS: GraphOptions = { ...INSTITUTIONS, papers: true };
  const edges = (graph: ReturnType<typeof buildGraph>) =>
    graph.links.map(({ source, target }) => `${source}->${target}`).sort();

  it("links each paper to its institutions when authors are hidden", () => {
    const graph = buildGraph(papers, PAPERS);

    expect(graph.nodes.map((node) => node.id)).toEqual([
      "institution:google",
      "institution:inria",
      "institution:tsinghua university",
      "paper:1",
      "paper:2",
      "paper:3",
    ]);
    expect(edges(graph)).toEqual([
      "institution:google->paper:1",
      "institution:google->paper:2",
      "institution:inria->paper:1",
      "institution:inria->paper:2",
      "institution:tsinghua university->paper:3",
    ]);
  });

  it("hangs institutions from the authors placed there, else from the paper", () => {
    const graph = buildGraph([mapped], { ...PAPERS, authors: true });

    // Ada is placed at Inria; nobody shown is placed at ETH, and Bob is not placed at all.
    expect(edges(graph)).toEqual([
      "author:ada->institution:inria",
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

    expect(edges(graph)).toEqual(["institution:eth zurich->paper:9", "institution:inria->paper:9"]);
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

describe("buildGraph with citations", () => {
  const cited = [
    makePaper({ arxiv_id: "1", authors: ["Ada"], affiliations: ["Inria"] }),
    makePaper({ arxiv_id: "2", authors: ["Ada", "Bob"], affiliations: ["Inria", "Google"] }),
    makePaper({ arxiv_id: "3", authors: ["Bob"], affiliations: ["Google"] }),
  ];
  const options: GraphOptions = {
    ...INSTITUTIONS,
    papers: true,
    authors: true,
    // Paper 3 has no known count: it adds nothing.
    citations: new Map([
      ["1", 10],
      ["2", 5],
    ]),
  };
  const citationsOf = (graph: ReturnType<typeof buildGraph>) =>
    Object.fromEntries(graph.nodes.map((node) => [node.id, node.citations]));

  it("sums the citations of each node's papers", () => {
    expect(citationsOf(buildGraph(cited, options))).toEqual({
      "institution:inria": 15,
      "institution:google": 5,
      "author:ada": 15,
      "author:bob": 5,
      "paper:1": 10,
      "paper:2": 5,
      "paper:3": 0,
    });
  });

  it("counts nothing without citation counts", () => {
    const { citations: _, ...uncounted } = options;
    expect(buildGraph(cited, uncounted).nodes.every((node) => node.citations === 0)).toBe(true);
  });
});

describe("replaySteps", () => {
  const daysOf = (first: string, count: number) =>
    Array.from({ length: count }, (_, index) => {
      const date = new Date(`${first}T00:00:00Z`);
      date.setUTCDate(date.getUTCDate() + index);
      return date.toISOString().slice(0, 10);
    });

  it("stops at every day of a short period", () => {
    const days = daysOf("2026-09-01", MAX_REPLAY_STEPS);
    expect(replaySteps(days)).toEqual(days);
  });

  it("stops at the last day of each week of a longer one", () => {
    // 2024-01-01 is a Monday: 70 days are ten weeks.
    const steps = replaySteps(daysOf("2024-01-01", 70));
    expect(steps).toHaveLength(10);
    expect(steps.slice(0, 2)).toEqual(["2024-01-07", "2024-01-14"]);
  });

  it("stops at the last day of each month of a year and more", () => {
    const steps = replaySteps(daysOf("2024-01-01", 500));
    expect(steps).toHaveLength(17);
    expect(steps.slice(0, 2)).toEqual(["2024-01-31", "2024-02-29"]);
  });
});

describe("matchStatus", () => {
  it("says how many nodes match, and which one is shown", () => {
    expect(matchStatus(0, null, null)).toBe("No match");
    expect(matchStatus(1, null, null)).toBe(
      "1 match: Enter shows them one by one, Shift+Enter backwards",
    );
    expect(matchStatus(12, 2, "MIT")).toBe("3 of 12 matches: MIT");
    expect(matchStatus(12, 2, null)).toBe("3 of 12 matches");
  });
});

describe("names that seem to be several people", () => {
  const AUTHORS: GraphOptions = { ...INSTITUTIONS, institutions: false, authors: true };
  const wang = (arxiv_id: string, id: string | null, institution: string, coauthor = "Ada") =>
    makePaper({
      arxiv_id,
      authors: ["Wei Wang", coauthor],
      author_ids: [id, null],
      affiliations: [institution],
      institutions: [institution],
      author_affiliations: [[0], null],
    });

  it("counts profiles that share no institution and no co-author as other people", () => {
    const graph = buildGraph(
      [
        // Two profiles of one person, at one institution.
        wang("1", "42", "Tsinghua University", "Ada"),
        wang("2", "43", "Tsinghua University", "Bob"),
        // Another Wei Wang, elsewhere, with other co-authors.
        wang("3", "7", "Zhejiang University", "Cyd"),
        wang("4", "7", "Zhejiang University", "Cyd"),
        // A profile of one paper: perhaps an orphan duplicate.
        wang("5", "9", "Peking University", "Dee"),
        wang("6", null, "Peking University", "Dee"),
      ],
      AUTHORS,
    );
    const node = graph.nodes.find((each) => each.label === "Wei Wang");

    expect(node?.paperIds.length).toBe(6);
    expect(node?.people).toBe(2);
    expect(graph.nodes.find((each) => each.label === "Ada")?.people).toBeUndefined();
  });

  it("joins profiles through a shared co-author", () => {
    const profile = (institutions: string[], coauthors: string[]) => ({
      institutions: new Set(institutions),
      coauthors: new Set(coauthors),
      papers: 2,
    });
    expect(countPeople([profile(["A"], ["x"]), profile(["B"], ["x"]), profile(["C"], ["y"])])).toBe(
      2,
    );
    expect(countPeople([profile([], []), profile([], [])])).toBe(2);
    expect(countPeople([])).toBe(0);
  });
});

describe("a node's papers and its connections", () => {
  const graph = buildGraph(papers, { ...INSTITUTIONS, authors: true });
  const node = (id: string) => {
    const found = graph.nodes.find((candidate) => candidate.id === id);
    if (!found) throw new Error(`no node ${id}`);
    return found;
  };

  it("are the papers two nodes share", () => {
    expect(sharedPapers(node("institution:inria"), node("institution:google"))).toEqual(["1", "2"]);
    expect(sharedPapers(node("author:bob"), node("institution:inria"))).toEqual(["1"]);
    expect(sharedPapers(node("author:cyd"), node("institution:inria"))).toEqual([]);
  });

  it("are the papers of a node, as the graph keys it", () => {
    const ids = (id: string) => papersOfNode(papers, id).map((paper) => paper.arxiv_id);
    expect(ids("institution:inria")).toEqual(["1", "2"]);
    expect(ids("author:ada")).toEqual(["1", "2"]);
    expect(ids("paper:3")).toEqual(["3"]);
    expect(ids("institution:nowhere")).toEqual([]);
    expect(ids("venue:cvpr")).toEqual([]);
    // A link written by hand means the node keyed alike.
    expect(ids("institution:Inria")).toEqual(["1", "2"]);
    expect(ids("author:ADA")).toEqual(["1", "2"]);
    // Its ego network: the institutions and authors of its papers alone.
    const ego = buildGraph(papersOfNode(papers, "author:bob"), { ...INSTITUTIONS, authors: true });
    expect(ego.nodes.map((entry) => entry.id).sort()).toEqual([
      "author:ada",
      "author:bob",
      "institution:google",
      "institution:inria",
    ]);
  });
});

describe("nodeLabel", () => {
  it("names a node by its most frequent spelling among the papers, or not at all", () => {
    const spelled = [
      makePaper({
        arxiv_id: "1",
        authors: ["José Ruiz"],
        affiliations: ["MIT"],
        institutions: ["MIT"],
      }),
      makePaper({
        arxiv_id: "2",
        authors: ["Jose Ruiz"],
        affiliations: ["mit"],
        institutions: ["mit"],
      }),
      makePaper({
        arxiv_id: "3",
        authors: ["José Ruiz"],
        affiliations: ["MIT"],
        institutions: ["MIT"],
      }),
    ];
    expect(nodeLabel(spelled, "author:jose ruiz")).toBe("José Ruiz");
    expect(nodeLabel(spelled, "institution:mit")).toBe("MIT");
    expect(nodeLabel(spelled, "institution:nowhere")).toBeNull();
    expect(nodeLabel(spelled, "paper:1")).toBeNull();
  });
});

describe("linkPapers", () => {
  // Ann is placed at Google on paper 1 only; Google and MIT sign all three.
  const placed = [
    makePaper({
      arxiv_id: "1",
      authors: ["Ann", "Bo"],
      affiliations: ["MIT", "Google"],
      author_affiliations: [[1], [0]],
    }),
    makePaper({
      arxiv_id: "2",
      authors: ["Ann", "Bo"],
      affiliations: ["MIT", "Google"],
      author_affiliations: [[0], [1]],
    }),
    makePaper({
      arxiv_id: "3",
      authors: ["Ann", "Bo"],
      affiliations: ["MIT", "Google"],
      author_affiliations: [[0], [1]],
    }),
  ];
  const byId = new Map(placed.map((paper) => [paper.arxiv_id, paper]));
  const projection: GraphOptions = { ...INSTITUTIONS, authors: true };
  const graph = buildGraph(placed, projection);
  const node = (id: string) => {
    const found = graph.nodes.find((candidate) => candidate.id === id);
    if (!found) throw new Error(`no node ${id}`);
    return found;
  };
  const weight = (a: string, b: string) =>
    graph.links.find(
      (link) =>
        (link.source === a && link.target === b) || (link.source === b && link.target === a),
    )?.weight;

  it("lists the papers a projection link counts, as many as its weight", () => {
    const papers = linkPapers(node("author:ann"), node("institution:google"), byId, projection);
    expect(papers).toEqual(["1"]);
    expect(weight("author:ann", "institution:google")).toBe(papers.length);
    expect(
      linkPapers(node("institution:mit"), node("institution:google"), byId, projection),
    ).toEqual(["1", "2", "3"]);
  });

  it("leaves out the papers of too many authors from co-authorship", () => {
    const authors = Array.from({ length: MAX_CLIQUE_AUTHORS + 1 }, (_, n) => `Author ${n}`);
    const consortium = [
      makePaper({ arxiv_id: "big", authors, affiliations: ["CERN"] }),
      makePaper({ arxiv_id: "small", authors: ["Author 0", "Author 1"], affiliations: ["CERN"] }),
    ];
    const options: GraphOptions = { ...INSTITUTIONS, authors: true };
    const big = buildGraph(consortium, options);
    const pick = (id: string) => big.nodes.find((candidate) => candidate.id === id);
    const [a, b] = [pick("author:author 0"), pick("author:author 1")];
    if (!(a && b)) throw new Error("authors missing");
    const lookup = new Map(consortium.map((paper) => [paper.arxiv_id, paper]));
    expect(linkPapers(a, b, lookup, options)).toEqual(["small"]);
  });

  it("is every shared paper when papers are nodes", () => {
    const options: GraphOptions = { ...INSTITUTIONS, papers: true, authors: true };
    const withPapers = buildGraph(placed, options);
    const pick = (id: string) => withPapers.nodes.find((candidate) => candidate.id === id);
    const [ann, google] = [pick("author:ann"), pick("institution:google")];
    if (!(ann && google)) throw new Error("nodes missing");
    expect(linkPapers(ann, google, byId, options)).toEqual(["1", "2", "3"]);
  });
});

describe("nodeConnections order", () => {
  it("puts the most shared first, then the node of more papers", () => {
    // Inria shares one paper with Google and one with MIT; MIT has two papers of its own.
    const tied = [
      makePaper({ arxiv_id: "1", affiliations: ["Inria", "Google"] }),
      makePaper({ arxiv_id: "2", affiliations: ["Inria", "MIT"] }),
      makePaper({ arxiv_id: "3", affiliations: ["MIT"] }),
    ];
    const options: GraphOptions = { ...INSTITUTIONS, papers: true, isolated: true };
    const graph = buildGraph(tied, options);
    const inria = graph.nodes.find((node) => node.id === "institution:inria");
    if (!inria) throw new Error("no Inria");
    expect(
      nodeConnections(graph, inria, entitiesByPaper(graph), 10).map(({ node }) => node.id),
    ).toEqual(["institution:mit", "institution:google"]);
    // In the projection too, by weight then papers.
    const projection = buildGraph(tied, { ...INSTITUTIONS, isolated: true });
    const inriaAgain = projection.nodes.find((node) => node.id === "institution:inria");
    if (!inriaAgain) throw new Error("no Inria");
    expect(nodeConnections(projection, inriaAgain, null, 10).map(({ node }) => node.id)).toEqual([
      "institution:mit",
      "institution:google",
    ]);
  });
});

describe("nodeConnections", () => {
  it("are the entities a node shares papers with, when papers are nodes", () => {
    const options: GraphOptions = { ...INSTITUTIONS, papers: true, authors: true };
    const graph = buildGraph(papers, options);
    const inria = graph.nodes.find((node) => node.id === "institution:inria");
    if (!inria) throw new Error("no Inria");
    const connections = nodeConnections(graph, inria, entitiesByPaper(graph), 10);
    expect(connections.map(({ node, weight }) => [node.id, weight])).toEqual([
      ["author:ada", 2],
      ["institution:google", 2],
      ["author:bob", 1],
    ]);
    expect(nodeConnections(graph, inria, entitiesByPaper(graph), 1)).toHaveLength(1);
  });

  it("are the nodes a node's links reach in the projection, by weight", () => {
    const graph = buildGraph(papers, { ...INSTITUTIONS, authors: true });
    const ada = graph.nodes.find((node) => node.id === "author:ada");
    if (!ada) throw new Error("no Ada");
    const connections = nodeConnections(graph, ada, null, 10);
    expect(connections[0]?.weight).toBe(2);
    expect(connections.map(({ node }) => node.id).sort()).toEqual([
      "author:bob",
      "institution:google",
      "institution:inria",
    ]);
  });
});

describe("canonicalNodeId", () => {
  it("keys a hand-written id as the graph does, and leaves a paper's alone", () => {
    expect(canonicalNodeId("institution:MIT")).toBe("institution:mit");
    expect(canonicalNodeId("author:José Ruiz")).toBe("author:jose ruiz");
    expect(canonicalNodeId("paper:2609.00001")).toBe("paper:2609.00001");
  });
});
