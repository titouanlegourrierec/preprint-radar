import { describe, expect, it } from "vitest";
import { rankEntities } from "../src/rankings";
import { exactly, matchesFilters, NO_FILTERS } from "../src/search";
import { makePaper } from "./fixtures";

const papers = [
  makePaper({ arxiv_id: "1", authors: ["Ada", "Bob"], affiliations: ["MIT", "Google"] }),
  makePaper({
    arxiv_id: "2",
    authors: ["Ada"],
    affiliations: ["Massachusetts Institute of Technology"],
  }),
  makePaper({ arxiv_id: "3", authors: ["Bob", "Carl"], affiliations: ["Google Research", "Bob"] }),
];
const citations = new Map([
  ["1", 3],
  ["3", 40],
]);
const rows = (metric: "papers" | "citations", kind: "institution" | "author" = "institution") =>
  rankEntities(papers, kind, metric, citations).map((entity) => [
    entity.name,
    entity.papers,
    entity.citations,
    entity.top.arxiv_id,
  ]);

describe("rankEntities", () => {
  it("merges institutions as the graph does, most papers first", () => {
    expect(rows("papers")).toEqual([
      ["Google", 2, 43, "3"],
      ["Massachusetts Institute of Technology", 2, 3, "1"],
    ]);
  });

  it("ranks by citations, papers breaking ties", () => {
    expect(rows("citations", "author")).toEqual([
      ["Bob", 2, 43, "3"],
      ["Carl", 1, 40, "3"],
      ["Ada", 2, 3, "1"],
    ]);
  });

  it("gives the most cited paper and its count, the first one when none is known", () => {
    const [ada] = rankEntities([...papers].slice(0, 2).reverse(), "author", "papers", new Map());
    expect(ada?.top.arxiv_id).toBe("2");
    expect(ada?.topCitations).toBeUndefined();
  });
});

describe("a row of Rankings and the papers it shows", () => {
  // Names that the substring filter confused: people inside other names, institutions
  // inside longer ones, the same institution written three ways, a collective author.
  const tricky = [
    makePaper({ arxiv_id: "1", authors: ["Hao Li", "Wei Wang"], affiliations: ["Intel Labs"] }),
    makePaper({
      arxiv_id: "2",
      authors: ["Chuanhao Li", "Weiwei Wang"],
      affiliations: ["Institute of Artificial Intelligence", "The Chinese University of Hong Kong"],
    }),
    makePaper({
      arxiv_id: "3",
      authors: ["HAO LI", "Yuhao Liu"],
      affiliations: ["Dept. of CS, The University of Hong Kong", "CMU"],
    }),
    makePaper({
      arxiv_id: "4",
      authors: ["Intel", "Hao Lin"],
      affiliations: ["Intel", "Carnegie Mellon University, Pittsburgh, PA"],
      institutions: [null, "Carnegie Mellon University"],
    }),
    makePaper({ arxiv_id: "5", authors: ["Wei Wang"], affiliations: ["University of Hong Kong"] }),
  ];

  it.each(["institution", "author"] as const)("counts as many %ss as the filter keeps", (kind) => {
    const ranked = rankEntities(tricky, kind, "papers", new Map());
    expect(ranked.length).toBeGreaterThan(3);
    for (const row of ranked) {
      const filters = {
        ...NO_FILTERS,
        [kind === "institution" ? "affiliation" : "author"]: exactly(row.name),
      };
      const shown = tricky.filter((paper) => matchesFilters(paper, filters));
      expect([row.name, shown.length]).toEqual([row.name, row.papers]);
    }
  });
});
