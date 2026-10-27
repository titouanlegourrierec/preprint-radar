import { afterEach, describe, expect, it, vi } from "vitest";
import { forgetLoaded, loadDays } from "../src/data";
import { PAPER_BUDGET } from "../src/period";
import { ANY_VENUE, exactly, NO_FILTERS, PaperIndex, typed } from "../src/search";
import { candidateTest, type StoreProgress, searchStore } from "../src/store-search";
import { makePaper } from "./fixtures";

/** Serve `files` (path under data/ -> JSON body); anything else is a 404. */
function serve(files: Record<string, unknown>, status: Record<string, number> = {}) {
  const requested: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    const path = url.slice(url.indexOf("data/") + "data/".length);
    requested.push(path);
    const code = status[path] ?? (path in files ? 200 : 404);
    return new Response(JSON.stringify(files[path] ?? {}), { status: code });
  });
  return requested;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  forgetLoaded();
});

function dayFile(date: string, papers = 1) {
  return {
    schema_version: 1,
    papers: Array.from({ length: papers }, (_, n) => makePaper({ arxiv_id: `${date}.${n}` })),
  };
}

describe("candidateTest (PROD-21)", () => {
  const stored = [
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
      venue: "NeurIPS 2026",
    }),
    makePaper({
      arxiv_id: "2609.00003",
      title: "Robot Grasping with Vision",
      abstract: "Grasping objects using novel view synthesis priors.",
      comments: "Code: https://github.com/example/grasping",
      affiliations: [],
    }),
    makePaper({
      arxiv_id: "2609.00004",
      title: "Semantic Segmentaton of Street Scenes",
      abstract: "Täxonomy-free scene parsing.",
      authors: ["Matthias Nießner"],
    }),
    makePaper({ arxiv_id: "2609.00005", title: "Gaussian Processes", venue: "CVPR 2025" }),
  ];
  const storeIndex = new PaperIndex(stored);
  const passing = (query: string, filters = NO_FILTERS) => {
    const test = candidateTest(query, filters);
    return stored.filter((paper) => test?.(paper)).map(({ arxiv_id }) => arxiv_id);
  };

  it("asks for a word or a filter, without which every paper would pass", () => {
    expect(candidateTest("", NO_FILTERS)).toBeNull();
    expect(candidateTest("the of", NO_FILTERS)).toBeNull();
    expect(candidateTest("-survey", NO_FILTERS)).toBeNull();
    expect(passing("", { ...NO_FILTERS, venue: ANY_VENUE })).toEqual(["2609.00002", "2609.00005"]);
  });

  it("lets through every paper the index finds", () => {
    const queries = [
      "gaussian",
      "gaussian splatting",
      "splat",
      "semantic segmentation",
      "segmentatoin",
      "niessner",
      "nießner",
      "lozano perez",
      '"novel view synthesis"',
      "video -survey",
      "nerf OR gaussian",
      'robot OR "diffusion models"',
      "massachusetts",
      "mit",
      "arXiv:2609.00002v2",
      "grasping github",
      "cvpr 2025",
      "taxonomy",
    ];
    const filterSets = [
      NO_FILTERS,
      { ...NO_FILTERS, affiliation: typed("MIT") },
      { ...NO_FILTERS, author: exactly("Jane Doe") },
      { ...NO_FILTERS, withCode: true },
    ];
    let found = 0;
    for (const query of queries) {
      for (const filters of filterSets) {
        const test = candidateTest(query, filters);
        for (const { paper } of storeIndex.search(query, filters, "relevance")) {
          found++;
          expect(test?.(paper), `${query} ${JSON.stringify(filters)}`).toBe(true);
        }
      }
    }
    expect(found).toBeGreaterThan(30);
  });

  it("lets a typo through, as the index matches one, by a half of the word", () => {
    expect(storeIndex.search("segmentation", NO_FILTERS, "relevance")).toHaveLength(1);
    expect(passing("segmentation")).toEqual(["2609.00004"]);
    expect(passing("parsinng")).toEqual(["2609.00004"]);
  });

  it("leaves out the papers without the words, and those the filters leave out", () => {
    expect(passing("diffusion")).toEqual(["2609.00002"]);
    expect(passing("gaussian")).toEqual(["2609.00001", "2609.00005"]);
    expect(passing("gaussian", { ...NO_FILTERS, venue: "CVPR*" })).toEqual(["2609.00005"]);
    expect(passing("nerf OR robot")).toEqual(["2609.00003"]);
    expect(passing("2609.00003")).toEqual(["2609.00003"]);
  });
});

describe("searchStore (PROD-21)", () => {
  const titled = (arxiv_id: string, title: string) => makePaper({ arxiv_id, title });
  const file = (...papers: ReturnType<typeof makePaper>[]) => ({ schema_version: 1, papers });
  const holding = {
    days: [
      { date: "2026-09-11", count: 2 },
      { date: "2026-09-10", count: 1 },
    ],
    archiveYears: [2017, 2019],
    topRecent: true,
  };
  const store = {
    "cs.CV/2026-09-11.json": file(titled("a", "Gaussian day"), titled("b", "Other")),
    "cs.CV/2026-09-10.json": file(titled("c", "Gaussian too")),
    "cs.CV/top-recent.json": file(titled("a", "Gaussian recent"), titled("d", "Gaussian older")),
    "cs.CV/archive/2019.json": file(titled("e", "Gaussian 2019"), titled("d", "Gaussian again")),
    "cs.CV/archive/2017.json": file(titled("f", "Other 2017")),
  };
  const gaussian = (paper: { title: string }) => paper.title.startsWith("Gaussian");

  it("reads every file newest first, a paper once, its day file's record", async () => {
    const requested = serve(store);
    const reads: StoreProgress[] = [];
    const found = await searchStore("cs.CV", holding, gaussian, (read) => reads.push(read));
    expect(requested).toEqual([
      "cs.CV/2026-09-11.json",
      "cs.CV/2026-09-10.json",
      "cs.CV/top-recent.json",
      "cs.CV/archive/2019.json",
      "cs.CV/archive/2017.json",
    ]);
    expect(found.papers.map(({ title }) => title)).toEqual([
      "Gaussian day",
      "Gaussian too",
      "Gaussian older",
      "Gaussian 2019",
    ]);
    expect(found).toMatchObject({
      searched: 6,
      leftOut: 0,
      missing: { days: [], years: [], recent: false },
    });
    // How far it went (UX-51): a paper of two files read twice, passed once.
    expect(reads).toEqual([
      { read: 2, found: 1 },
      { read: 3, found: 2 },
      { read: 5, found: 3 },
      { read: 7, found: 4 },
      { read: 8, found: 4 },
    ]);
  });

  it("reads the files a period loaded from memory", async () => {
    const requested = serve(store);
    await loadDays("cs.CV", [{ date: "2026-09-11", count: 2 }]);
    await searchStore("cs.CV", { ...holding, topRecent: false }, gaussian, () => undefined);
    expect(requested.filter((path) => path === "cs.CV/2026-09-11.json")).toHaveLength(1);
    expect(requested).not.toContain("cs.CV/top-recent.json");
  });

  it("keeps a budget of papers, counting those that pass past it", async () => {
    serve({
      "cs.CV/2026-09-11.json": dayFile("2026-09-11", PAPER_BUDGET + 2),
    });
    const found = await searchStore(
      "cs.CV",
      {
        days: [{ date: "2026-09-11", count: PAPER_BUDGET + 2 }],
        archiveYears: [],
        topRecent: false,
      },
      () => true,
      () => undefined,
    );
    expect(found.papers).toHaveLength(PAPER_BUDGET);
    expect(found.leftOut).toBe(2);
    expect(found.searched).toBe(PAPER_BUDGET + 2);
  });

  it("asks for a failed file once more, then names it; fails when no file loads", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const failing = {
      "cs.CV/2026-09-10.json": 503,
      "cs.CV/top-recent.json": 503,
      "cs.CV/archive/2017.json": 503,
    };
    const requested = serve(store, failing);
    const found = await searchStore("cs.CV", holding, gaussian, () => undefined);
    expect(found.missing).toEqual({ days: ["2026-09-10"], years: [2017], recent: true });
    expect(requested.filter((path) => path === "cs.CV/archive/2017.json")).toHaveLength(2);
    expect(found.papers.map(({ arxiv_id }) => arxiv_id)).toEqual(["a", "e", "d"]);

    serve({}, { "cs.CV/2026-09-11.json": 503 });
    await expect(
      searchStore(
        "cs.CV",
        { days: [{ date: "2026-09-11", count: 2 }], archiveYears: [], topRecent: false },
        gaussian,
        () => undefined,
      ),
    ).rejects.toThrow("Could not load cs.CV/2026-09-11.json (HTTP 503)");
  });

  it("fails on a file of another schema version, and once the search is left", async () => {
    serve({ ...store, "cs.CV/archive/2019.json": { schema_version: 2, papers: [] } });
    await expect(searchStore("cs.CV", holding, gaussian, () => undefined)).rejects.toThrow(
      "Unsupported data file schema version 2",
    );
    serve(store);
    const left = new AbortController();
    left.abort();
    await expect(
      searchStore("cs.CV", holding, gaussian, () => undefined, left.signal),
    ).rejects.toThrow();
  });

  it("lets the page draw between files that come at once", async () => {
    serve(store);
    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => (now += 40));
    const found = await searchStore("cs.CV", holding, gaussian, () => undefined);
    expect(found.papers).toHaveLength(4);
  });

  it("finds nothing in an empty store", async () => {
    serve({});
    const empty = { days: [], archiveYears: [], topRecent: false };
    await expect(searchStore("cs.CV", empty, gaussian, () => undefined)).resolves.toMatchObject({
      papers: [],
      searched: 0,
    });
  });
});
