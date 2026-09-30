import { describe, expect, it } from "vitest";
import { rankEntities } from "../src/rankings";
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
