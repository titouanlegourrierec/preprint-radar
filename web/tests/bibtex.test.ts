import { describe, expect, it } from "vitest";
import { citationKey, toBibtex } from "../src/bibtex";
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
        "  title = {Towards Practical Compression of 3D Gaussian Splatting},",
        "  author = {Pengpeng Yu and Yulan Guo},",
        "  year = {2026},",
        "  eprint = {2609.30245},",
        "  archivePrefix = {arXiv},",
        "  primaryClass = {cs.CV},",
        "  url = {https://arxiv.org/abs/2609.30245},",
        "}",
      ].join("\n"),
    );
  });
});
