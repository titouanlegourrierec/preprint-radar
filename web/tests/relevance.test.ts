/**
 * Search relevance on cases met in the real data (TEST-16): each one names the wrong result
 * an earlier version gave. The other search tests check the mechanics; these pin what a
 * reader expects to find.
 */
import { describe, expect, it } from "vitest";
import { arxivIdOf, exactly, NO_FILTERS, PaperIndex, typed } from "../src/search";
import { makePaper } from "./fixtures";

const corpus = new PaperIndex([
  makePaper({
    arxiv_id: "2609.10001",
    announced: "2026-09-25",
    title: "GAN Inversion for Image Editing",
    authors: ["Wei Li", "Ana Pérez"],
    affiliations: ["National University of Singapore"],
  }),
  makePaper({
    arxiv_id: "2609.10002",
    announced: "2026-09-25",
    title: "Robust Monocular Depth Estimation",
    abstract: "Depth estimation in the wild, without death of performance.",
    authors: ["Yiwei Liu", "Yu Gan"],
    affiliations: ["HKUST"],
  }),
  makePaper({
    arxiv_id: "2609.10003",
    announced: "2026-09-24",
    title: "Zero-Shot Segmentation with Vision Transformers",
    abstract: "A ViT for open-vocabulary segmentation, mitigating label noise.",
    authors: ["Hao Li", "Weiwei Wang"],
    affiliations: ["MIT", "Intel Labs"],
  }),
  makePaper({
    arxiv_id: "2609.10004",
    announced: "2026-09-24",
    title: "A zero shot survey of on-device vision",
    authors: ["Chuanhao Li"],
    affiliations: ["Institute of Artificial Intelligence, Peking University"],
  }),
  makePaper({
    arxiv_id: "1706.03762",
    announced: "2017-06-12",
    title: "Attention Is All You Need",
    authors: ["Ashish Vaswani"],
    affiliations: ["Google"],
  }),
]);

const found = (query: string, filters = NO_FILTERS) =>
  corpus.search(query, filters, "relevance").map(({ paper }) => paper.arxiv_id);

describe("relevance on real cases", () => {
  it("finds a person, not the names that contain theirs", () => {
    expect(found("Wei Li")).toEqual(["2609.10001"]);
    expect(found("", { ...NO_FILTERS, author: exactly("Hao Li") })).toEqual(["2609.10003"]);
  });

  it("finds acronyms as words: GAN papers before authors named Gan", () => {
    expect(found("gan")).toEqual(["2609.10001", "2609.10002"]);
    expect(found("mit")).toEqual(["2609.10003"]);
    expect(found("vit")).toEqual(["2609.10003"]);
  });

  it("finds hyphenated words with or without the hyphen, in quotes or not", () => {
    expect(found('"zero shot"').sort()).toEqual(["2609.10003", "2609.10004"]);
    expect(found("zero-shot").sort()).toEqual(["2609.10003", "2609.10004"]);
  });

  it("does not find a word one typo away from a short one", () => {
    expect(found("depth")).toEqual(["2609.10002"]);
    expect(found("death")).toEqual(["2609.10002"]);
    expect(found("detph")).toEqual([]);
  });

  it("finds a paper from its arXiv identifier or link", () => {
    for (const query of [
      "2609.10003",
      "arXiv:2609.10003v2",
      " https://arxiv.org/abs/2609.10003 ",
      "arxiv.org/pdf/2609.10003v1.pdf",
    ]) {
      expect(found(query, { ...NO_FILTERS, author: typed("nobody") })).toEqual(["2609.10003"]);
    }
    expect(found("2609.99999")).toEqual([]);
    expect(arxivIdOf("cs/0601001v2")).toBe("cs/0601001");
    expect(arxivIdOf("2609.10003 gaussian")).toBeNull();
  });

  it("keeps every paper for stop words alone, as while typing on-device", () => {
    expect(found("the")).toHaveLength(5);
    expect(found("on")).toHaveLength(5);
    expect(found("on-device")).toEqual(["2609.10004"]);
  });

  it("filters institutions by acronym and by clicked name", () => {
    const at = (affiliation: ReturnType<typeof typed>) =>
      found("", { ...NO_FILTERS, affiliation }).sort();
    expect(at(typed("nus"))).toEqual(["2609.10001"]);
    expect(at(typed("hku"))).toEqual([]);
    // Intel Labs is Intel; "Institute of Artificial Intelligence" is not.
    expect(at(exactly("Intel"))).toEqual(["2609.10003"]);
    expect(at(typed("intel"))).toEqual(["2609.10003", "2609.10004"]);
  });
});
