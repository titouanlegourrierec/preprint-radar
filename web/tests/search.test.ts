import { describe, expect, it } from "vitest";
import { highlight, wholeWord } from "../src/highlight";
import {
  ANY_VENUE,
  affiliationNeedles,
  alphabetical,
  byCitations,
  byGains,
  byStars,
  exactly,
  matchesFilters,
  NO_FILTERS,
  nameHighlights,
  PaperIndex,
  parseQuery,
  type SearchResult,
  startsWords,
  subjectFacets,
  subjectsOf,
  typed,
  valueCounts,
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
    institutions: ["Massachusetts Institute of Technology", "NVIDIA"],
  }),
  makePaper({
    arxiv_id: "2609.00002",
    title: "Diffusion Models for Video Generation",
    abstract: "A survey of video diffusion models.",
    affiliations: ["MIT"],
    institutions: ["Massachusetts Institute of Technology"],
    cross_list_from: "cs.LG",
    venue: "NeurIPS 2026",
    primary_subject: "Machine Learning (cs.LG)",
    subjects: ["Machine Learning (cs.LG)", "Computer Vision and Pattern Recognition (cs.CV)"],
  }),
  makePaper({
    arxiv_id: "2609.00003",
    title: "Robot Grasping with Vision",
    abstract: "Grasping objects using novel view synthesis priors.",
    comments: "Code: https://github.com/example/grasping",
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
    expect(ids("", { ...NO_FILTERS, withCode: true })).toEqual(["2609.00003"]);
  });

  it("filters by venue, or keeps every paper accepted somewhere", () => {
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS 2026" })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: ANY_VENUE })).toEqual(["2609.00002"]);
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS" })).toEqual([]);
    expect(ids("", { ...NO_FILTERS, venue: "NeurIPS*" })).toEqual(["2609.00002"]);
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
      makePaper({
        arxiv_id: "2",
        affiliations: ["NUS"],
        institutions: ["National University of Singapore"],
      }),
      makePaper({
        arxiv_id: "3",
        affiliations: ["School of Computing, Singapore"],
        institutions: [null],
      }),
      makePaper({
        arxiv_id: "4",
        affiliations: ["Dept. of CS, University College London, UK"],
        institutions: ["University College London"],
      }),
      makePaper({
        arxiv_id: "5",
        affiliations: ["HKUST"],
        institutions: ["Hong Kong University of Science and Technology"],
      }),
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
      makePaper({
        arxiv_id: "1",
        affiliations: ["Intel Labs, Santa Clara"],
        institutions: ["Intel"],
      }),
      makePaper({
        arxiv_id: "2",
        affiliations: ["Institute of Artificial Intelligence, Peking University"],
        institutions: ["Peking University"],
      }),
      makePaper({
        arxiv_id: "3",
        affiliations: ["The Chinese University of Hong Kong"],
        institutions: ["Chinese University of Hong Kong"],
      }),
      makePaper({
        arxiv_id: "4",
        affiliations: ["Dept. of CS, The University of Hong Kong"],
        institutions: ["University of Hong Kong"],
      }),
      // A collective listed among the affiliations is an author, not an institution.
      makePaper({
        arxiv_id: "5",
        authors: ["Intel"],
        affiliations: ["Intel"],
        institutions: [null],
      }),
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

  it("leaves the names filtered on out of the results' highlights (SRCH-8)", () => {
    const [result] = index.search("", { ...NO_FILTERS, author: exactly("Jane Doe") }, "newest");
    expect(result?.highlights).toEqual([]);
  });

  it("highlights a typed filter's words but its stop words, as word starts, in its line", () => {
    expect(nameHighlights({ ...NO_FILTERS, affiliation: typed("University of Tokyo") })).toEqual({
      authors: [],
      affiliations: ["university", "tokyo"],
      institution: null,
    });
    const typedHao = nameHighlights({ ...NO_FILTERS, author: typed("hao") });
    expect(typedHao.affiliations).toEqual([]);
    expect(highlight("Haoran Li", typedHao.authors).some((segment) => segment.match)).toBe(true);
    expect(nameHighlights({ ...NO_FILTERS, author: typed("  ") }).authors).toEqual([]);
  });

  it("highlights a clicked name as a whole, not words starting like it", () => {
    const needles = nameHighlights({
      ...NO_FILTERS,
      author: exactly("Hao Li"),
      affiliation: exactly("NVIDIA"),
    });
    expect(needles).toEqual({
      authors: [wholeWord("hao li")],
      affiliations: [wholeWord("nvidia")],
      institution: "nvidia",
    });
    const marked = (text: string, terms: readonly string[]) =>
      highlight(text, terms)
        .filter((segment) => segment.match)
        .map((segment) => segment.text);
    expect(marked("A lightweight linear model for limited data", needles.authors)).toEqual([]);
    expect(marked("Hao Li, Jane Doe", needles.authors)).toEqual(["Hao Li"]);
    expect(marked("NVIDIA Research", needles.affiliations)).toEqual(["NVIDIA"]);
  });

  it("marks whole the affiliations of a clicked institution, however they write it", () => {
    const paper = makePaper({
      arxiv_id: "1",
      affiliations: ["IIT Kanpur", "Some Lab"],
      institutions: ["Indian Institute of Technology Kanpur", null],
    });
    const names = nameHighlights({
      ...NO_FILTERS,
      affiliation: exactly("Indian Institute of Technology Kanpur"),
    });
    const marked = (affiliation: string) =>
      highlight(affiliation, affiliationNeedles(paper, affiliation, names, ["lab"]))
        .filter((segment) => segment.match)
        .map((segment) => segment.text);
    expect(marked("IIT Kanpur")).toEqual(["IIT Kanpur"]);
    // Only the search words mark another affiliation.
    expect(marked("Some Lab")).toEqual(["Lab"]);
  });

  it("keeps a typed word whole across its punctuation", () => {
    const marked = (typedText: string, text: string) =>
      highlight(text, nameHighlights({ ...NO_FILTERS, affiliation: typed(typedText) }).affiliations)
        .filter((segment) => segment.match)
        .map((segment) => segment.text);
    expect(marked("AT&T", "AT&T Labs Research")).toEqual(["AT&T"]);
    expect(marked("Xi'an", "Xi\u2019an Jiaotong University")).toEqual(["Xi\u2019an"]);
    expect(marked("Jean-Luc", "Luca Rossi")).toEqual([]);
    expect(marked("Jean-Luc", "Jean-Luc Starck")).toEqual(["Jean-Luc"]);
    // The pieces of a typed word start words, as the filter reads them.
    expect(marked("Univ-of-Tokyo", "University of Tokyo")).toEqual(["University of Tokyo"]);
  });

  it("marks a typed name whose pieces start words, as the filter keeps it", () => {
    const filters = { ...NO_FILTERS, author: typed("J.Smith") };
    const paper = makePaper({ arxiv_id: "1", authors: ["John Smith", "Jane Doe"] });
    const marked = (text: string, needles: string[]) =>
      highlight(text, needles)
        .filter((segment) => segment.match)
        .map((segment) => segment.text);
    expect(matchesFilters(paper, filters)).toBe(true);
    expect(marked("John Smith, Jane Doe", nameHighlights(filters).authors)).toEqual(["John Smith"]);
    // An initial alone marks nothing.
    const initial = nameHighlights({ ...NO_FILTERS, author: typed("J. Smith") }).authors;
    expect(marked("John Smith, Jane Doe", initial)).toEqual(["Smith"]);
  });

  it("matches a clicked name across its punctuation, as the filter does", () => {
    const marked = (name: string, text: string) =>
      highlight(text, nameHighlights({ ...NO_FILTERS, author: exactly(name) }).authors)
        .filter((segment) => segment.match)
        .map((segment) => segment.text);
    expect(marked("Julia A. Schnabel", "Julia A Schnabel")).toEqual(["Julia A Schnabel"]);
    expect(marked("Xi'an Jiaotong University", "Xi\u2019an Jiaotong University")).toEqual([
      "Xi\u2019an Jiaotong University",
    ]);
  });

  it("reports matched terms for highlighting", () => {
    const [result] = index.search("splatting", NO_FILTERS, "relevance");
    expect(result?.highlights).toContain("splatting");
  });

  it("deduplicates papers present in several days", () => {
    expect(new PaperIndex([...papers, ...papers]).size).toBe(3);
  });
});

describe("PaperIndex building", () => {
  // The first paper and the last, which a first chunk does not reach, have their own word.
  const titles: Record<number, string> = { 3: "Zebra crossings", 449: "Quokka habitats" };
  const many = Array.from({ length: 450 }, (_, n) =>
    makePaper({ arxiv_id: `2609.${String(n).padStart(5, "0")}`, title: titles[n] ?? "Filler" }),
  );

  it("indexes nothing until a search has words", () => {
    const lazy = new PaperIndex(many);
    expect(lazy.ready).toBe(false);
    expect(lazy.search("", NO_FILTERS, "newest")).toHaveLength(450);
    expect(lazy.get("2609.00449")?.title).toBe("Quokka habitats");
    expect(lazy.ready).toBe(false);
    expect(lazy.search("quokka", NO_FILTERS, "relevance")).toHaveLength(1);
    expect(lazy.ready).toBe(true);
  });

  it("warms in chunks, and a search adds the papers left", async () => {
    const warmed = new PaperIndex(many);
    await warmed.warm();
    expect(warmed.ready).toBe(true);

    const stopped = new PaperIndex(many);
    const stop = new AbortController();
    const warming = stopped.warm(stop.signal);
    stop.abort();
    await warming;
    // The first chunk went in before the signal was read again.
    expect(stopped.ready).toBe(false);
    expect(stopped.search("quokka", NO_FILTERS, "relevance")).toHaveLength(1);
    expect(stopped.search("zebra", NO_FILTERS, "relevance")).toHaveLength(1);
    expect(stopped.ready).toBe(true);
    await stopped.warm();
    expect(stopped.search("quokka", NO_FILTERS, "relevance")).toHaveLength(1);
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

describe("valueCounts", () => {
  it("counts values across papers, most frequent first", () => {
    expect(valueCounts(papers, (paper) => paper.affiliations ?? [], 5)).toEqual([
      { value: "MIT", count: 2 },
      { value: "NVIDIA", count: 1 },
    ]);
  });
});

describe("subjects", () => {
  const CV = "Computer Vision and Pattern Recognition (cs.CV)";
  const LG = "Machine Learning (cs.LG)";
  const RO = "Robotics (cs.RO)";
  const crossListed = makePaper({ arxiv_id: "2609.00012", subjects: [CV, LG, RO] });
  // Saved in a browser before `subjects` was kept.
  const saved = makePaper({ arxiv_id: "2609.00015", primary_subject: LG, subjects: [] });
  const listed = [
    makePaper({ arxiv_id: "2609.00011", subjects: [CV, RO] }),
    crossListed,
    makePaper({ arxiv_id: "2609.00013", primary_subject: RO, subjects: [RO, CV] }),
    makePaper({ arxiv_id: "2609.00014" }),
    saved,
  ];
  const subjectIndex = new PaperIndex(listed);
  const under = (subject: string) =>
    subjectIndex
      .search("", { ...NO_FILTERS, subject }, "newest")
      .map(({ paper }) => paper.arxiv_id)
      .sort();

  it("filters on a subject the paper is listed under, primary or cross-listed", () => {
    expect(under(RO)).toEqual(["2609.00011", "2609.00012", "2609.00013"]);
    expect(under(LG)).toEqual(["2609.00012", "2609.00015"]);
    expect(under("Quantum Physics (quant-ph)")).toEqual([]);
    expect(subjectsOf(saved)).toEqual([LG]);
    expect(subjectsOf(crossListed)).toEqual([CV, LG, RO]);
  });

  it("counts every paper's subjects, whichever is chosen", () => {
    const counts = [
      { value: CV, count: 4 },
      { value: RO, count: 3 },
      { value: LG, count: 2 },
    ];
    expect(subjectFacets(listed, null, 10)).toEqual(counts);
    expect(subjectFacets(listed, RO, 10)).toEqual(counts);
  });

  it("keeps the subject chosen listed, past the limit or held by no paper", () => {
    expect(subjectFacets(listed, LG, 1)).toEqual([
      { value: CV, count: 4 },
      { value: LG, count: 2 },
    ]);
    expect(subjectFacets(listed, "Quantum Physics (quant-ph)", 1)).toEqual([
      { value: CV, count: 4 },
      { value: "Quantum Physics (quant-ph)", count: 0 },
    ]);
  });

  it("compares subjects by code, as the archive writes some and a link may hold one", () => {
    const archived = makePaper({
      arxiv_id: "1801.00001",
      subjects: ["cs.RO"],
      primary_subject: "cs.RO",
    });
    const mixed = [...listed, archived];
    expect(
      new PaperIndex(mixed).search("", { ...NO_FILTERS, subject: "cs.RO" }, "newest"),
    ).toHaveLength(4);
    expect(new PaperIndex(mixed).search("", { ...NO_FILTERS, subject: RO }, "newest")).toHaveLength(
      4,
    );
    // One choice per code, named in full, holding the value the link holds when chosen.
    expect(subjectFacets(mixed, null, 10)).toContainEqual({ value: RO, count: 4 });
    expect(subjectFacets(mixed, "cs.RO", 10)).toContainEqual({ value: "cs.RO", count: 4 });
    expect(
      subjectFacets(mixed, "cs.RO", 10).filter(({ value }) => value.includes("cs.RO")),
    ).toHaveLength(1);
  });
});

describe("Most cited and Rising with search words", () => {
  // Tied counts, as on recent days: the best match first, not the newest (CIT-6).
  const tied = new PaperIndex([
    makePaper({ arxiv_id: "2609.00021", announced: "2026-09-24", title: "Diffusion priors" }),
    makePaper({
      arxiv_id: "2609.00022",
      announced: "2026-09-25",
      title: "Robust depth",
      comments: "A diffusion baseline",
    }),
    makePaper({ arxiv_id: "2609.00023", announced: "2026-09-23", title: "Fast stereo" }),
  ]);
  const counts = new Map([
    ["2609.00021", 0],
    ["2609.00022", 0],
    ["2609.00023", 0],
  ]);
  const order = (results: readonly SearchResult[]) => results.map(({ paper }) => paper.arxiv_id);

  it("keeps relevance among equal counts", () => {
    const cited = byCitations(tied.search("diffusion", NO_FILTERS, "citations"), counts);
    expect(order(cited)).toEqual(["2609.00021", "2609.00022"]);
    const rising = byGains(tied.search("diffusion", NO_FILTERS, "rising"), new Map(), counts);
    expect(order(rising)).toEqual(["2609.00021", "2609.00022"]);
    // A higher count still comes first.
    const more = new Map([...counts, ["2609.00022", 3]]);
    expect(order(byCitations(tied.search("diffusion", NO_FILTERS, "citations"), more))).toEqual([
      "2609.00022",
      "2609.00021",
    ]);
  });

  it("orders by date without search words, or when asked for the newest", () => {
    expect(order(tied.search("diffusion", NO_FILTERS, "newest"))).toEqual([
      "2609.00022",
      "2609.00021",
    ]);
    expect(order(byCitations(tied.search("", NO_FILTERS, "citations"), counts))).toEqual([
      "2609.00022",
      "2609.00021",
      "2609.00023",
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

describe("byGains", () => {
  it("ranks results by citations gained, then by citations", () => {
    const results = ["a", "b", "c", "d"].map((id) => ({
      paper: makePaper({ arxiv_id: id }),
      score: 0,
      highlights: [],
    }));
    const counts = new Map([
      ["a", 5],
      ["b", 10],
      ["c", 250],
      ["d", 10],
    ]);
    const gains = new Map([
      ["a", 3],
      ["d", 4],
    ]);

    expect(byGains(results, gains, counts).map(({ paper }) => paper.arxiv_id)).toEqual([
      "d",
      "a",
      "c",
      "b",
    ]);
  });
});

describe("Most starred (PROD-18)", () => {
  const index = new PaperIndex([
    makePaper({ arxiv_id: "2609.00031", announced: "2026-09-25", code: { stars: 12 } }),
    makePaper({ arxiv_id: "2609.00032", announced: "2026-09-24", code: { stars: 900 } }),
    // Shared: a monorepo's stars, not the paper's.
    makePaper({
      arxiv_id: "2609.00033",
      announced: "2026-09-23",
      code: { stars: 30_000, shared: true },
    }),
    makePaper({ arxiv_id: "2609.00034", announced: "2026-09-22", code: { likes: 4 } }),
    makePaper({ arxiv_id: "2609.00035", announced: "2026-09-21" }),
    makePaper({ arxiv_id: "2609.00036", announced: "2026-09-20", code: { stars: 12 } }),
  ]);

  it("ranks the most starred first, the shared with those without stars, ties newest first", () => {
    const ranked = byStars(index.search("", NO_FILTERS, "stars")).map(
      ({ paper }) => paper.arxiv_id,
    );
    expect(ranked).toEqual([
      "2609.00032",
      "2609.00031",
      "2609.00036",
      "2609.00033",
      "2609.00034",
      "2609.00035",
    ]);
  });
});
