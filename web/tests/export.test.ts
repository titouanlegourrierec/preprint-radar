import { describe, expect, it } from "vitest";
import { toCsv, toMarkdown, toRis } from "../src/export";
import { archiveYearLabel, categoryName, daysSince } from "../src/format";
import { byCitations, mostlyTied, type SearchResult } from "../src/search";
import { makePaper } from "./fixtures";

const paper = makePaper({
  arxiv_id: "2609.30245",
  announced: "2026-09-25",
  title: 'A "quoted", comma title',
  authors: ["Ada Lovelace", "Bob Smith", "Carl Gauss", "Dora Maar"],
  affiliations: ["MIT", "ETH Zurich"],
  abstract: "An abstract\non two lines.",
  venue: "ECCV 2026",
});

describe("exports", () => {
  it("write CSV, quoting what needs it", () => {
    const lines = toCsv([paper], new Map([["2609.30245", 3]])).split("\r\n");
    expect(lines[0]).toBe("arxiv_id,title,authors,affiliations,announced,venue,doi,citations,url");
    expect(lines[1]).toBe(
      '2609.30245,"A ""quoted"", comma title",Ada Lovelace; Bob Smith; Carl Gauss; Dora Maar,MIT; ETH Zurich,2026-09-25,ECCV 2026,,3,https://arxiv.org/abs/2609.30245',
    );
    expect(toCsv([{ ...paper, doi: "10.1/x" }], new Map()).split("\r\n")[1]).toContain(
      ",ECCV 2026,10.1/x,,",
    );
  });

  it("write RIS records with the arXiv DOI", () => {
    const ris = toRis([paper]);
    expect(ris).toContain("TY  - UNPB\r\n");
    expect(ris).toContain("AU  - Dora Maar\r\n");
    expect(ris).toContain("DO  - 10.48550/arXiv.2609.30245\r\n");
    expect(ris).toContain("N1  - Accepted to ECCV 2026\r\n");
    expect(ris.trimEnd().endsWith("ER  -")).toBe(true);
    // The published version's DOI, when known.
    expect(toRis([{ ...paper, doi: "10.1109/CVPR.2026.1" }])).toContain(
      "DO  - 10.1109/CVPR.2026.1\r\n",
    );
  });

  it("write a Markdown list", () => {
    expect(toMarkdown([paper])).toBe(
      '- [A "quoted", comma title](https://arxiv.org/abs/2609.30245) — Ada Lovelace, Bob Smith, Carl Gauss et al. (arXiv:2609.30245, ECCV 2026)\n',
    );
  });
});

describe("naming and dating", () => {
  it("names a category", () => {
    expect(categoryName("cs.CV")).toBe("cs.CV (Computer Vision and Pattern Recognition)");
    expect(categoryName("q-bio.NC")).toBe("q-bio.NC");
  });

  it("labels the youngest archive year by the months it holds", () => {
    const asOf = new Date(2026, 9, 3);
    expect(archiveYearLabel(2025, asOf)).toMatch(/^2025, .+–.+$/);
    expect(archiveYearLabel(2024, asOf)).toBe("2024");
    expect(archiveYearLabel(2025, new Date(2027, 0, 5))).toBe("2025");
  });

  it("counts days", () => {
    expect(daysSince("2026-09-25", new Date(2026, 9, 3, 12))).toBe(8);
  });
});

describe("citations order", () => {
  const result = (arxivId: string): SearchResult => ({
    paper: makePaper({ arxiv_id: arxivId }),
    score: 0,
    highlights: [],
  });

  it("puts unknown counts after zeros, keeping the order of ties", () => {
    const counts = new Map([
      ["b", 0],
      ["c", 5],
      ["d", 0],
    ]);
    expect(
      byCitations(["a", "b", "c", "d"].map(result), counts).map(({ paper }) => paper.arxiv_id),
    ).toEqual(["c", "b", "d", "a"]);
  });

  it("says when most results share one count", () => {
    const ids = Array.from({ length: 20 }, (_, n) => `p${n}`);
    expect(mostlyTied(ids.map(result), new Map([["p0", 4]]))).toBe(true);
    expect(mostlyTied(ids.map(result), new Map(ids.slice(0, 5).map((id, n) => [id, n + 1])))).toBe(
      false,
    );
    expect(mostlyTied(ids.slice(0, 5).map(result), new Map())).toBe(false);
  });
});

describe("exports of sparse records", () => {
  const bare = makePaper({
    arxiv_id: "2609.00001",
    title: "Short [title]",
    authors: ["Ada Lovelace"],
  });

  it("leave out what a record lacks", () => {
    expect(toCsv([bare], new Map()).split("\r\n")[1]).toBe(
      "2609.00001,Short [title],Ada Lovelace,,2026-09-25,,,,https://arxiv.org/abs/2609.00001",
    );
    const ris = toRis([bare]);
    expect(ris).not.toContain("AB  -");
    expect(ris).not.toContain("N1  -");
    expect(toMarkdown([bare])).toBe(
      "- [Short \\[title\\]](https://arxiv.org/abs/2609.00001) — Ada Lovelace (arXiv:2609.00001)\n",
    );
  });
});
