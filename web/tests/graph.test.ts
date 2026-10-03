import { describe, expect, it } from "vitest";
import { buildGraph, type GraphOptions, nodeMatches } from "../src/graph";
import { canonicalInstitution, institutionName, paperInstitutions } from "../src/institutions";
import { searchKey } from "../src/text";
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
    ["KAIST", "Korea Advanced Institute of Science and Technology"],
    ["Meta", "Meta"],
    ["and", ""],
    // Units and addresses alone name no institution.
    ["Department of Computer Science", ""],
    ["College of Computer Science and Electronic Engineering", ""],
    ["Nagoya 461-8680", ""],
    ["Independent Researcher", ""],
    ["Independent Researcher, University of Regensburg", "University of Regensburg"],
    ["Independent Author", ""],
    ["Independent researchers", ""],
    // Leftovers that older data still holds: they must not become institution nodes.
    ["Correspondence", ""],
    ["the", ""],
    ["Code", ""],
    ["Core Contributors", ""],
    ["USA", ""],
    ["United Kingdom", ""],
    ["Tencent, China", "Tencent"],
    // Companies, however written; a hospital is not its sponsor.
    ["NVIDIA AI Technology Centre, Singapore", "NVIDIA"],
    ["ARC Lab, Tencent IEG", "Tencent"],
    ["Microsoft Research Asia, Shanghai, China", "Microsoft"],
    ["Samsung Medical Center", "Samsung Medical Center"],
    ["Zhiyang Innovation Co., Ltd", "Zhiyang Innovation Co. Ltd"],
    // Acronyms and campuses.
    ["MIT, Boston, USA", "Massachusetts Institute of Technology"],
    ["CASIA", "Chinese Academy of Sciences"],
    ["University of California, Berkeley", "University of California, Berkeley"],
    ["EECS, University of California, Los Angeles, CA", "University of California, Los Angeles"],
    ["Luca Gandolfi and Chiara Plizzari are with Bocconi University", "Bocconi University"],
  ])("%s -> %s", (affiliation, expected) => {
    expect(institutionName(affiliation)).toBe(expected);
  });
});

describe("paperInstitutions", () => {
  it("prefers the registry's institution, and names the others locally", () => {
    const paper = makePaper({
      arxiv_id: "20",
      affiliations: ["University of Padova, Italy", "CMU", "Microsoft Research Asia, Beijing"],
      institutions: ["University of Padua", null, "Microsoft Research Asia"],
    });

    expect(paperInstitutions(paper)).toEqual([
      "University of Padua",
      "Carnegie Mellon University",
      "Microsoft",
    ]);
  });

  it("ignores institutions that do not match the affiliations one to one", () => {
    const paper = makePaper({
      arxiv_id: "21",
      affiliations: ["MIT", "Inria"],
      institutions: ["X"],
    });

    expect(paperInstitutions(paper)).toEqual(["Massachusetts Institute of Technology", "Inria"]);
  });

  it("maps a company, as the registry spells it, to its common name", () => {
    expect(canonicalInstitution("Google DeepMind")).toBe("Google DeepMind");
    expect(canonicalInstitution("Tencent (China)")).toBe("Tencent");
    expect(canonicalInstitution("Peking University")).toBe("Peking University");
  });
});

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

  it("never makes an institution of one of the paper's authors", () => {
    const listed = makePaper({
      arxiv_id: "12",
      authors: ["Dong Liang", "Ada"],
      affiliations: ["Dong Liang", "Inria"],
    });

    expect(buildGraph([listed], INSTITUTIONS).nodes.map((node) => node.label)).toEqual(["Inria"]);
  });

  it("can hide nodes that share no paper with another node", () => {
    const graph = buildGraph(papers, { ...INSTITUTIONS, isolated: false });

    expect(graph.nodes.map((node) => node.label)).toEqual(["Google", "Inria"]);
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
