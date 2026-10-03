import { describe, expect, it } from "vitest";
import { bibtexTitle, citationKey, toBibtex, toBibtexFile } from "../src/bibtex";
import { makePaper } from "./fixtures";

const paper = makePaper({
  arxiv_id: "2609.30245",
  title: "Towards Practical Compression of 3D Gaussian Splatting",
  authors: ["Pengpeng Yu", "Yulan Guo"],
});

describe("bibtex", () => {
  it("builds a citation key from surname, year and first significant word", () => {
    expect(citationKey(paper)).toBe("yu2026practical");
  });

  it("renders an arXiv @misc entry", () => {
    expect(toBibtex(paper)).toBe(
      [
        "@misc{yu2026practical,",
        "  title = {Towards Practical Compression of {3D} Gaussian Splatting},",
        "  author = {Pengpeng Yu and Yulan Guo},",
        "  year = {2026},",
        "  eprint = {2609.30245},",
        "  archivePrefix = {arXiv},",
        "  primaryClass = {cs.CV},",
        "  doi = {10.48550/arXiv.2609.30245},",
        "  url = {https://arxiv.org/abs/2609.30245},",
        "}",
      ].join("\n"),
    );
  });

  // Real titles of September 2026.
  it.each([
    [
      "0.5%>100%: Bidirectional Reciprocal Learning for Referring Image Segmentation",
      "0.5\\%>100\\%: Bidirectional Reciprocal Learning for Referring Image Segmentation",
    ],
    [
      "G^2RA-NET: Graph-based Cross-Slice Relation",
      "{G\\^{}2RA-NET:} Graph-based Cross-Slice Relation",
    ],
    ["Brains & Machines: R_1 Losses #2", "Brains \\& Machines: {R\\_1} Losses \\#2"],
    ["Already 50\\% escaped", "Already 50\\% escaped"],
    ["S$^2$Prune: Pruning for Multimodal LLMs", "S$^2$Prune: Pruning for Multimodal {LLMs}"],
    ["Reweighted $\\ell_1$ Penalties", "Reweighted $\\ell_1$ Penalties"],
    [
      "NeRF and CLIP for Text-to-3D with iPhone",
      "{NeRF} and {CLIP} for {Text-to-3D} with {iPhone}",
    ],
  ])("escapes and protects %s", (title, expected) => {
    expect(bibtexTitle(title)).toBe(expected);
  });

  it("leaves a suffix out of the surname of the key", () => {
    expect(citationKey({ ...paper, authors: ["Eduil Nascimento Jr."] })).toBe(
      "nascimento2026practical",
    );
    expect(citationKey({ ...paper, authors: ["John Smith III"] })).toBe("smith2026practical");
  });

  it("adds the venue a paper was accepted at", () => {
    expect(toBibtex({ ...paper, venue: "ECCV 2026" })).toContain(
      "  note = {Accepted to ECCV 2026},",
    );
  });

  it("tells colliding keys apart in a file, in the order of identifiers", () => {
    const twin = { ...paper, arxiv_id: "2609.10000" };
    const other = makePaper({ arxiv_id: "2609.20000", title: "Other", authors: ["Ada Lovelace"] });
    const file = toBibtexFile([paper, other, twin]);
    expect([...file.matchAll(/@misc\{([^,]+),/g)].map((match) => match[1])).toEqual([
      "yu2026practicalb",
      "lovelace2026other",
      "yu2026practicala",
    ]);
  });
});
