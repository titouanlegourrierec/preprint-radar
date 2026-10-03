import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  loadReadingList,
  mergePapers,
  readingListFile,
  readPapers,
  refreshPapers,
  saveReadingList,
  toPaper,
} from "../src/reading-list";
import { makePaper } from "./fixtures";

const ada = makePaper({ arxiv_id: "2609.00001", authors: ["Ada"], affiliations: ["MIT"] });
const bob = makePaper({ arxiv_id: "2609.00002", authors: ["Bob"] });

describe("toPaper", () => {
  it("keeps a stored record as it is", () => {
    expect(toPaper(JSON.parse(JSON.stringify(ada)))).toEqual(ada);
  });

  it.each([
    ["not an object", "2609.00001"],
    ["no identifier", { ...ada, arxiv_id: 12 }],
    ["no date", { ...ada, announced: "yesterday" }],
    ["authors not a list", { ...ada, authors: "Ada" }],
    ["no links", { ...ada, abs_url: undefined }],
  ])("refuses a record with %s", (_, record) => {
    expect(toPaper(record)).toBeNull();
  });

  it("fills what older records lack, and drops a mapping out of step", () => {
    const { subjects: _, venue: __, ...older } = { ...ada, author_affiliations: [[0], [1]] };
    const paper = toPaper(older);
    expect(paper?.subjects).toEqual([]);
    expect(paper?.venue).toBeNull();
    expect(paper?.author_affiliations).toBeNull();
    expect(toPaper({ ...ada, author_affiliations: [[3]] })?.author_affiliations).toBeNull();
    expect(toPaper({ ...ada, author_affiliations: [[0]] })?.author_affiliations).toEqual([[0]]);
  });
});

describe("readPapers", () => {
  it("reads the current format and the bare array of the first versions", () => {
    expect(readPapers(readingListFile([ada, bob])).papers).toEqual([ada, bob]);
    expect(readPapers([ada, bob]).papers).toEqual([ada, bob]);
  });

  it("skips what is not a paper, and keeps a paper once", () => {
    expect(readPapers([ada, { title: "x" }, ada, null])).toEqual({ papers: [ada], skipped: 2 });
    expect(readPapers({ something: "else" })).toEqual({ papers: [], skipped: 0 });
  });
});

describe("merging and refreshing", () => {
  it("adds the imported papers not saved yet, after the saved ones", () => {
    expect(mergePapers([ada], [bob, ada])).toEqual({ papers: [ada, bob], added: 1 });
  });

  it("takes the fresher record of a loaded day", () => {
    const pending = { ...bob, affiliations: null };
    const read = { ...bob, affiliations: ["ETH Zurich"] };
    const saved = [ada, pending];
    expect(refreshPapers(saved, (id) => (id === bob.arxiv_id ? read : undefined))).toEqual([
      ada,
      read,
    ]);
    expect(refreshPapers(saved, () => undefined)).toBe(saved);
  });
});

describe("storage", () => {
  const stored = new Map<string, string>();
  beforeEach(() => {
    stored.clear();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => {
        if (value.length > 2000) throw new DOMException("full", "QuotaExceededError");
        stored.set(key, value);
      },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("stores a versioned list, and reads the bare array stored before", () => {
    expect(saveReadingList([ada])).toBe(true);
    expect(JSON.parse(stored.get("preprint-radar:reading-list") ?? "")).toMatchObject({
      version: 1,
    });
    expect(loadReadingList()).toEqual([ada]);
    stored.set("preprint-radar:reading-list", JSON.stringify([bob, { broken: true }]));
    expect(loadReadingList()).toEqual([bob]);
  });

  it("says when the browser refuses to store the list", () => {
    const many = Array.from({ length: 20 }, (_, n) => ({
      ...ada,
      arxiv_id: `2609.${String(n).padStart(5, "0")}`,
    }));
    expect(saveReadingList(many)).toBe(false);
  });
});
