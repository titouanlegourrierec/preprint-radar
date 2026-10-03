import { describe, expect, it } from "vitest";
import { wholeWord } from "../src/highlight";
import {
  ANY_VENUE,
  alphabetical,
  byCitations,
  exactly,
  facetCounts,
  matchesFilters,
  NO_FILTERS,
  PaperIndex,
  parseQuery,
  startsWords,
  typed,
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

  it("requires all terms, the last one as a prefix of 4 letters or more", () => {
    expect(ids("gaussian compress")).toEqual(["2609.00001"]);
    // Only the word being typed is a prefix.
    expect(ids("gauss compression")).toEqual([]);
  });

  it("ignores stop words and tolerates a typo in long words", () => {
    expect(ids("difusion for video")).toEqual(["2609.00002"]);
    expect(ids("viedo")).toEqual([]);
  });

  it("treats short acronyms and names as whole words", () => {
    const acronyms = new PaperIndex([
      makePaper({ arxiv_id: "1", title: "GAN inversion", authors: ["Ada Lovelace"] }),
      makePaper({ arxiv_id: "2", title: "Robust depth", authors: ["Yu Gan", "Mahatma Gandhi"] }),
      makePaper({ arxiv_id: "3", title: "Mitigating death in ViT training" }),
      makePaper({ arxiv_id: "4", title: "Vittorio's viterbi decoder" }),
    ]);
    const found = (query: string) =>
      acronyms
        .search(query, NO_FILTERS, "newest")
        .map(({ paper }) => paper.arxiv_id)
        .sort();

    expect(found("gan")).toEqual(["1", "2"]);
    expect(found("mit")).toEqual([]);
    expect(found("vit")).toEqual(["3"]);
    expect(found("depth")).toEqual(["2"]);
    const [hit] = acronyms.search("depth", NO_FILTERS, "relevance");
    expect(hit?.highlights).toEqual(["depth"]);
    const [vit] = acronyms.search("vit", NO_FILTERS, "relevance");
    expect(vit?.highlights).toEqual([wholeWord("vit")]);
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
    expect(ids("", { ...NO_FILTERS, affiliation: typed("NVIDIA") })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, author: exactly("Jane Doe") })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, subject: "Machine Learning (cs.LG)" })).toEqual(["2609.00002"]);
  });

  it("filters by venue, or keeps every paper accepted somewhere", () => {
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS 2026" })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: ANY_VENUE })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS" })).toEqual([]);
  });

  it("matches typed filters at the start of words, ignoring case and accents", () => {
    expect(ids("", { ...NO_FILTERS, affiliation: typed("nvid") })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, affiliation: typed("mit") }).sort()).toEqual([
      "2609.00001",
      "2609.00002",
    ]);
    expect(ids("", { ...NO_FILTERS, author: typed("perez") })).toEqual(["2609.00001"]);
    expect(ids("", { ...NO_FILTERS, author: typed("  ") })).toHaveLength(3);
    expect(ids("", { ...NO_FILTERS, author: exactly("") })).toHaveLength(3);
    // Inside a word is not the start of one.
    expect(ids("", { ...NO_FILTERS, affiliation: typed("vidia") })).toEqual([]);
  });

  it.each([
    ["KAIST, Daejeon", "kaist", true],
    ["Tomás Lozano-Pérez", "perez", true],
    ["Hao Lin", "hao li", true],
    ["Chuanhao Li", "hao li", false],
    ["Yiwei Liu", "wei li", false],
    ["Li Hao", "hao li", false],
    ["Massachusetts Institute of Technology", "institute of tech", true],
    ["Intelligent Systems Lab", "intel", true],
  ])("typed text %s ~ %s", (value, text, expected) => {
    expect(startsWords(value, text)).toBe(expected);
  });

  it("finds an institution by its acronym, however its papers write it", () => {
    const named = [
      makePaper({ arxiv_id: "1", affiliations: ["National University of Singapore, Singapore"] }),
      makePaper({ arxiv_id: "2", affiliations: ["NUS"] }),
      makePaper({ arxiv_id: "3", affiliations: ["School of Computing, Singapore"] }),
      makePaper({ arxiv_id: "4", affiliations: ["Dept. of CS, University College London, UK"] }),
      makePaper({ arxiv_id: "5", affiliations: ["HKUST"] }),
      makePaper({ arxiv_id: "6", affiliations: ["HKU-TCL Joint Lab"] }),
    ];
    const kept = (text: string) =>
      named
        .filter((paper) => matchesFilters(paper, { ...NO_FILTERS, affiliation: typed(text) }))
        .map((paper) => paper.arxiv_id);

    expect(kept("nus")).toEqual(["1", "2"]);
    expect(kept("UCL")).toEqual(["4"]);
    // A known acronym is a whole word, not the start of another one.
    expect(kept("hku")).toEqual(["6"]);
    expect(kept("hkus")).toEqual(["5"]);
    // And the full name finds the acronym, through the institution it names.
    expect(kept("national univ")).toEqual(["1", "2"]);
  });

  it("matches a clicked author exactly, not the names that contain it", () => {
    const people = [
      makePaper({ arxiv_id: "1", authors: ["Hao Li"] }),
      makePaper({ arxiv_id: "2", authors: ["Chuanhao Li", "Hao Lin"] }),
      makePaper({ arxiv_id: "3", authors: ["Yuhao Liu", "HAO LI"] }),
    ];
    const kept = (filter: ReturnType<typeof exactly>) =>
      people
        .filter((paper) => matchesFilters(paper, { ...NO_FILTERS, author: filter }))
        .map((paper) => paper.arxiv_id);

    expect(kept(exactly("Hao Li"))).toEqual(["1", "3"]);
    expect(kept(typed("Hao Li"))).toEqual(["1", "2", "3"]);
  });

  it("matches a clicked institution by its name, not the strings that contain it", () => {
    const labs = [
      makePaper({ arxiv_id: "1", affiliations: ["Intel Labs, Santa Clara"] }),
      makePaper({
        arxiv_id: "2",
        affiliations: ["Institute of Artificial Intelligence, Peking University"],
      }),
      makePaper({ arxiv_id: "3", affiliations: ["The Chinese University of Hong Kong"] }),
      makePaper({ arxiv_id: "4", affiliations: ["Dept. of CS, The University of Hong Kong"] }),
      // A collective listed among the affiliations is an author, not an institution.
      makePaper({ arxiv_id: "5", authors: ["Intel"], affiliations: ["Intel"] }),
    ];
    const kept = (filter: ReturnType<typeof exactly>) =>
      labs
        .filter((paper) => matchesFilters(paper, { ...NO_FILTERS, affiliation: filter }))
        .map((paper) => paper.arxiv_id);

    expect(kept(exactly("Intel"))).toEqual(["1"]);
    expect(kept(exactly("University of Hong Kong"))).toEqual(["4"]);
    expect(kept(typed("University of Hong Kong"))).toEqual(["3", "4"]);
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
      named.search(
        query,
        { ...NO_FILTERS, affiliation: affiliation ? typed(affiliation) : null },
        "relevance",
      ).length;

    // "MIT" is named Massachusetts Institute of Technology, as in the graph.
    expect(
      ids("", { ...NO_FILTERS, affiliation: typed("Massachusetts Institute") }).sort(),
    ).toEqual(["2609.00001", "2609.00002"]);
    expect(
      ids("", {
        ...NO_FILTERS,
        affiliation: exactly("Massachusetts Institute of Technology"),
      }).sort(),
    ).toEqual(["2609.00001", "2609.00002"]);
    expect(find("", "University of Padua")).toBe(1);
    expect(find("padua")).toBe(1);
  });

  describe("phrases and exclusions", () => {
    const corpus = new PaperIndex([
      makePaper({
        arxiv_id: "1",
        title: "Self-Supervised Zero-Shot Segmentation",
        authors: ["Yu-Rou Tuan"],
        affiliations: ["Carnegie Mellon University, Pittsburgh"],
      }),
      makePaper({
        arxiv_id: "2",
        title: "A zero shot organ detector",
        affiliations: ["Google Research"],
      }),
      makePaper({ arxiv_id: "3", title: "GAN surveys", venue: "CVPR 2026" }),
    ]);
    const found = (query: string) =>
      corpus
        .search(query, NO_FILTERS, "newest")
        .map(({ paper }) => paper.arxiv_id)
        .sort();

    it("match phrases in every searched field", () => {
      expect(found('"Yu-Rou Tuan"')).toEqual(["1"]);
      expect(found('"carnegie mellon university"')).toEqual(["1"]);
      expect(found('"cvpr 2026"')).toEqual(["3"]);
    });

    it("match phrases as whole words, hyphens or not", () => {
      expect(found('"zero shot"')).toEqual(["1", "2"]);
      expect(found('"self supervised"')).toEqual(["1"]);
      expect(found('"self-supervised"')).toEqual(["1"]);
      expect(found('"gan"')).toEqual(["3"]);
      expect(found('"zero sh"')).toEqual([]);
    });

    it("leave out the papers with a word starting like an exclusion, in any field", () => {
      expect(found("-google")).toEqual(["1", "3"]);
      expect(found("-survey")).toEqual(["1", "2"]);
      expect(found("-self-supervised")).toEqual(["2", "3"]);
      expect(found("-tuan")).toEqual(["2", "3"]);
      expect(found("-!!")).toEqual(["1", "2", "3"]);
    });
  });

  it("does not highlight stop words of filters", () => {
    const tokyo = new PaperIndex([
      makePaper({ arxiv_id: "1", affiliations: ["University of Tokyo"] }),
    ]);
    const [result] = tokyo.search(
      "",
      { ...NO_FILTERS, affiliation: typed("University of Tokyo") },
      "newest",
    );
    expect(result?.highlights).toEqual(["university", "tokyo"]);
  });

  it("highlights the text of author and affiliation filters", () => {
    const [result] = index.search("", { ...NO_FILTERS, affiliation: typed("nvidia") }, "newest");
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

describe("byCitations", () => {
  it("ranks results by citation count, unknown counts last, keeping ties in order", () => {
    const results = ["a", "b", "c", "d"].map((id) => ({
      paper: makePaper({ arxiv_id: id }),
      score: 0,
      highlights: [],
    }));
    const counts = new Map([
      ["b", 10],
      ["c", 250],
      ["d", 10],
    ]);

    expect(byCitations(results, counts).map(({ paper }) => paper.arxiv_id)).toEqual([
      "c",
      "b",
      "d",
      "a",
    ]);
  });
});
