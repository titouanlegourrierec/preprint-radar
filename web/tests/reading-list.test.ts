import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  loadReadingList,
  mergePapers,
  movePaper,
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
    const published = { ...ada, doi: "10.1109/CVPR.2026.1" };
    expect(toPaper(JSON.parse(JSON.stringify(published)))).toEqual(published);
    const withdrawn = { ...ada, withdrawn: true };
    expect(toPaper(JSON.parse(JSON.stringify(withdrawn)))).toEqual(withdrawn);
    expect(toPaper({ ...ada, withdrawn: "yes" })).not.toHaveProperty("withdrawn");
  });

  it("keeps ROR ids that follow the institutions, and drops the others", () => {
    const named = {
      ...ada,
      affiliations: ["MIT", "Lab"],
      institutions: ["Massachusetts Institute of Technology", null],
      institution_ids: ["042nb2s44", null],
    };
    expect(toPaper(JSON.parse(JSON.stringify(named)))).toEqual(named);
    expect(toPaper({ ...named, institution_ids: ["042nb2s44"] })).not.toHaveProperty(
      "institution_ids",
    );
    expect(toPaper({ ...named, institutions: null })).not.toHaveProperty("institution_ids");
  });

  it.each([
    ["not an object", "2609.00001"],
    ["no identifier", { ...ada, arxiv_id: 12 }],
    ["no date", { ...ada, announced: "yesterday" }],
    ["authors not a list", { ...ada, authors: "Ada" }],
    ["an identifier that is a link", { ...ada, arxiv_id: "https://arxiv.org/abs/2609.00001" }],
    ["a versioned identifier", { ...ada, arxiv_id: "2609.00001v2" }],
  ])("refuses a record with %s", (_, record) => {
    expect(toPaper(record)).toBeNull();
  });

  it("makes its links from the identifier, never from the file (SEC-2)", () => {
    const hostile = {
      ...ada,
      abs_url: "javascript:alert(1)",
      pdf_url: "data:text/html,<script>alert(1)</script>",
      html_url: "javascript:alert(1)",
    };
    const paper = toPaper(hostile);
    expect(paper?.abs_url).toBe("https://arxiv.org/abs/2609.00001");
    expect(paper?.pdf_url).toBe("https://arxiv.org/pdf/2609.00001");
    expect(paper?.html_url).toBeNull();
    expect(toPaper({ ...ada, html_url: "/html/2609.00001" })?.html_url).toBeNull();
    expect(toPaper({ ...ada, html_url: "https://arxiv.org/html/2609.00001v1" })?.html_url).toBe(
      "https://arxiv.org/html/2609.00001v1",
    );
    const { abs_url: _, pdf_url: __, ...linkless } = ada;
    expect(toPaper(linkless)?.abs_url).toBe("https://arxiv.org/abs/2609.00001");
    expect(toPaper({ ...ada, arxiv_id: "cs/0601001" })?.pdf_url).toBe(
      "https://arxiv.org/pdf/cs/0601001",
    );
  });

  it("keeps the day file and the code of a search shard's record, as the build writes them", () => {
    const light = { ...ada, abstract: null, light: "cs.CV/2026-09-25.json", code_url: null };
    expect(toPaper(JSON.parse(JSON.stringify(light)))).toEqual(light);
    const coded = { ...light, code_url: "https://github.com/example/tool" };
    expect(toPaper(coded)).toEqual(coded);
    const hostile = toPaper({
      ...light,
      light: "https://example.org/x.json",
      code_url: "javascript:alert(1)",
    });
    expect(hostile).not.toHaveProperty("light");
    expect(hostile).not.toHaveProperty("code_url");
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
    // The folders go with the papers, when there are some (UX-38).
    const folders = [{ name: "To read", papers: [ada.arxiv_id] }];
    expect(readingListFile([ada], [], folders)).toEqual({ version: 1, papers: [ada], folders });
    expect(readingListFile([ada], [], [])).toEqual({ version: 1, papers: [ada] });
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

describe("movePaper", () => {
  const ids = (papers: { arxiv_id: string }[]) => papers.map((paper) => paper.arxiv_id.slice(-1));
  const list = ["1", "2", "3", "4"].map((n) => makePaper({ arxiv_id: `2609.0000${n}` }));

  it("moves a paper before or after another, the reading list's own order (UX-39)", () => {
    expect(ids(movePaper(list, "2609.00004", "2609.00002", "before"))).toEqual([
      "1",
      "4",
      "2",
      "3",
    ]);
    expect(ids(movePaper(list, "2609.00001", "2609.00003", "after"))).toEqual(["2", "3", "1", "4"]);
    expect(ids(movePaper(list, "2609.00002", "2609.00004", "after"))).toEqual(["1", "3", "4", "2"]);
  });

  it("leaves the list as it is when nothing moves", () => {
    expect(movePaper(list, "2609.00002", "2609.00003", "before")).toBe(list);
    expect(movePaper(list, "2609.00002", "2609.00001", "after")).toBe(list);
    expect(movePaper(list, "2609.00002", "2609.00002", "after")).toBe(list);
    expect(movePaper(list, "2609.00009", "2609.00001", "after")).toBe(list);
    expect(movePaper(list, "2609.00001", "2609.00009", "after")).toBe(list);
  });
});
