import { afterEach, describe, expect, it, vi } from "vitest";
import {
  citationShard,
  forgetLoaded,
  loadArchive,
  loadArchiveYears,
  loadCitationShard,
  loadCountries,
  loadDays,
  loadIndex,
  loadLightDays,
  loadPapersById,
  loadTopRecent,
  loadWholePaper,
} from "../src/data";
import { PAPER_BUDGET } from "../src/period";
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

describe("data", () => {
  it("loads the countries of the institutions, none before the first are written (UX-40)", async () => {
    const countries = {
      schema_version: 1,
      generated_at: "2026-10-16T05:00:00+00:00",
      source: "OpenAlex",
      institutions: { "03vek6s52": "US" },
    };
    serve({ "cs.CV/countries.json": countries });
    await expect(loadCountries("cs.CV")).resolves.toEqual(countries);
    serve({});
    await expect(loadCountries("cs.CV")).resolves.toBeNull();
    serve({ "cs.CV/countries.json": { ...countries, schema_version: 2 } });
    await expect(loadCountries("cs.CV")).rejects.toThrow("Unsupported countries schema version 2");
    serve({}, { "cs.CV/countries.json": 503 });
    await expect(loadCountries("cs.CV")).rejects.toThrow(
      "Could not load cs.CV/countries.json (HTTP 503)",
    );
  });

  it("loads the index, refusing another schema", async () => {
    serve({ "index.json": { schema_version: 1, generated_at: "x", categories: {} } });
    await expect(loadIndex()).resolves.toMatchObject({ schema_version: 1 });
    serve({ "index.json": { schema_version: 2, categories: {} } });
    await expect(loadIndex()).rejects.toThrow("Unsupported index schema version 2 (expected 1)");
    serve({});
    await expect(loadIndex()).rejects.toThrow("Could not load index.json (HTTP 404)");
  });

  it("loads days in order, a few at a time", async () => {
    const days = Array.from({ length: 9 }, (_, n) => ({
      date: `2026-09-${String(n + 10)}`,
      count: 1,
    }));
    const files = Object.fromEntries(
      days.map(({ date }) => [
        `cs.CV/${date}.json`,
        { schema_version: 1, papers: [makePaper({ arxiv_id: date })] },
      ]),
    );
    const requested = serve(files);

    const { papers, missing } = await loadDays("cs.CV", days);

    expect(papers.map(({ arxiv_id }) => arxiv_id)).toEqual(days.map(({ date }) => date));
    expect(missing).toEqual([]);
    expect(requested).toHaveLength(9);
    await expect(loadDays("cs.CV", [])).resolves.toEqual({ papers: [], missing: [] });
  });

  it("asks for a failed day file once more, then leaves its day out", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const requested: string[] = [];
    let dropped = 1;
    vi.stubGlobal("fetch", async (url: string) => {
      const path = url.slice(url.indexOf("data/") + "data/".length);
      requested.push(path);
      if (path === "cs.CV/2026-09-11.json") return new Response("{}", { status: 500 });
      if (path === "cs.CV/2026-09-10.json" && dropped-- > 0) throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify(dayFile(path.slice(6, 16))));
    });
    const days = ["2026-09-12", "2026-09-11", "2026-09-10"].map((date) => ({ date, count: 1 }));

    const { papers, missing } = await loadDays("cs.CV", days);

    // The tenth's dropped request was answered the second time; the eleventh never was.
    expect(papers.map(({ arxiv_id }) => arxiv_id)).toEqual(["2026-09-12.0", "2026-09-10.0"]);
    expect(missing).toEqual(["2026-09-11"]);
    expect(requested.filter((path) => path === "cs.CV/2026-09-10.json")).toHaveLength(2);
    expect(requested.filter((path) => path === "cs.CV/2026-09-11.json")).toHaveLength(2);
    expect(warn).toHaveBeenCalledExactlyOnceWith(
      "Could not load the day file cs.CV/2026-09-11.json",
      new Error("Could not load cs.CV/2026-09-11.json (HTTP 500)"),
    );
  });

  it("fails a period whose every day file fails", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    serve({}, { "cs.CV/2026-09-10.json": 500, "cs.CV/2026-09-11.json": 503 });
    await expect(
      loadDays("cs.CV", [
        { date: "2026-09-10", count: 0 },
        { date: "2026-09-11", count: 0 },
      ]),
    ).rejects.toThrow(/Could not load cs\.CV\/2026-09-1[01]\.json \(HTTP 50[03]\)/);
  });

  it("fails a period with a day file of another schema version, asked for once", async () => {
    const requested = serve({
      "cs.CV/2026-09-10.json": dayFile("2026-09-10"),
      "cs.CV/2026-09-11.json": { schema_version: 2, papers: [] },
    });
    await expect(
      loadDays("cs.CV", [
        { date: "2026-09-10", count: 1 },
        { date: "2026-09-11", count: 0 },
      ]),
    ).rejects.toThrow("Unsupported day file schema version 2 (expected 1)");
    expect(requested.filter((path) => path === "cs.CV/2026-09-11.json")).toHaveLength(1);
  });

  it("asks for nothing again once the period is left", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const controller = new AbortController();
    let requests = 0;
    vi.stubGlobal("fetch", async () => {
      requests++;
      controller.abort();
      throw new DOMException("The operation was aborted.", "AbortError");
    });

    await expect(
      loadDays("cs.CV", [{ date: "2026-09-10", count: 1 }], controller.signal),
    ).rejects.toThrow("The operation was aborted.");
    expect(requests).toBe(1);
    expect(warn).not.toHaveBeenCalled();
  });

  it("loads an archive year", async () => {
    serve({
      "cs.CV/archive/2017.json": {
        schema_version: 1,
        papers: [makePaper({ arxiv_id: "1706.03762" })],
      },
    });
    await expect(loadArchive("cs.CV", 2017)).resolves.toHaveLength(1);
  });

  it("loads the most cited papers of the last 12 months, refusing another schema", async () => {
    serve({
      "cs.CV/top-recent.json": {
        schema_version: 1,
        since: "2025-10-05",
        papers: [makePaper({ arxiv_id: "2511.21631" })],
      },
      "cs.RO/top-recent.json": { schema_version: 2, since: "2025-10-05", papers: [] },
    });
    await expect(loadTopRecent("cs.CV")).resolves.toHaveLength(1);
    await expect(loadTopRecent("cs.RO")).rejects.toThrow(
      "Unsupported top-recent file schema version 2",
    );
  });

  it("loads several archive years, the best ranked within the budget", async () => {
    const archive = (year: number, ids: string[]) => ({
      schema_version: 1,
      papers: ids.map((id) => makePaper({ arxiv_id: id, announced: `${year}-06-01` })),
    });
    const shard = (counts: Record<string, number>) => ({
      schema_version: 1,
      category: "cs.CV",
      generated_at: "2026-10-04T05:41:00+00:00",
      source: "S2",
      counts,
    });
    serve({
      "cs.CV/archive/2016.json": archive(2016, ["a", "b"]),
      "cs.CV/archive/2024.json": archive(2024, ["c", "d"]),
      // a: 1,000 in ten years; c: 400 in two, which ranks it first.
      "cs.CV/citations/2016.json": shard({ a: 1000, b: 10 }),
      "cs.CV/citations/2024.json": shard({ c: 400 }),
    });
    const ids = (papers: { arxiv_id: string }[]) => papers.map(({ arxiv_id }) => arxiv_id);

    const all = await loadArchiveYears("cs.CV", [2024, 2016], 10);
    expect(ids(all.papers)).toEqual(["c", "d", "a", "b"]);
    expect(all.total).toBe(4);

    const best = await loadArchiveYears("cs.CV", [2024, 2016], 2);
    expect(ids(best.papers)).toEqual(["c", "a"]);
    expect(best.total).toBe(4);
  });

  it("ranks without counts when the shards fail", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    serve(
      {
        "cs.CV/archive/2016.json": { schema_version: 1, papers: [makePaper({ arxiv_id: "a" })] },
        "cs.CV/archive/2017.json": { schema_version: 1, papers: [makePaper({ arxiv_id: "b" })] },
      },
      { "cs.CV/citations/2016.json": 500 },
    );
    const loaded = await loadArchiveYears("cs.CV", [2017, 2016], 1);
    expect(loaded.papers).toHaveLength(1);
    expect(loaded.total).toBe(2);
    expect(loaded.unranked).toBe(2);
    // The failure is reported; 2017's shard, which does not exist, is not.
    expect(warn).toHaveBeenCalledOnce();
  });

  it("reports a citation shard that fails in the console, and asks for it again", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const requested = serve({}, { "cs.CV/citations/2019.json": 503 });
    await expect(citationShard("cs.CV", "2019")).resolves.toBeNull();
    expect(warn).toHaveBeenCalledWith(
      "Could not load the citation shard cs.CV/citations/2019.json",
      expect.objectContaining({ message: "Could not load citation counts (HTTP 503)" }),
    );
    await expect(citationShard("cs.CV", "2019")).resolves.toBeNull();
    expect(requested).toEqual(["cs.CV/citations/2019.json", "cs.CV/citations/2019.json"]);

    // A shard that does not exist is no failure: no counts were published for it yet.
    warn.mockClear();
    await expect(citationShard("cs.CV", "2018")).resolves.toBeNull();
    expect(warn).not.toHaveBeenCalled();
  });

  it("ranks a paper without a count after those of none, and loads each shard once", async () => {
    const requested = serve({
      "cs.CV/archive/2016.json": {
        schema_version: 1,
        papers: [makePaper({ arxiv_id: "a", announced: "2016-06-01" })],
      },
      "cs.CV/archive/2017.json": {
        schema_version: 1,
        papers: [makePaper({ arxiv_id: "b", announced: "2017-06-01" })],
      },
      "cs.CV/citations/2016.json": {
        schema_version: 1,
        category: "cs.CV",
        generated_at: "2026-10-04T05:41:00+00:00",
        source: "S2",
        counts: { a: 0 },
      },
    });
    // 2017's shard is a 404: b's count is unknown, and ranks after a's 0.
    const loaded = await loadArchiveYears("cs.CV", [2017, 2016], 1);
    expect(loaded.papers.map(({ arxiv_id }) => arxiv_id)).toEqual(["a"]);
    expect(loaded.unranked).toBe(1);
    await citationShard("cs.CV", "2016");
    expect(requested.filter((path) => path === "cs.CV/citations/2016.json")).toHaveLength(1);
  });

  it("keeps the files loaded for the next periods, within the budget", async () => {
    const requested = serve({
      "cs.CV/2026-09-10.json": dayFile("2026-09-10", 3),
      "cs.CV/2026-09-11.json": dayFile("2026-09-11", PAPER_BUDGET),
      "cs.CV/archive/2017.json": dayFile("1706", 2),
    });
    const tenth = [{ date: "2026-09-10", count: 3 }];
    await loadDays("cs.CV", tenth);
    await loadArchive("cs.CV", 2017);
    await loadDays("cs.CV", tenth);
    await loadArchive("cs.CV", 2017);
    expect(requested).toEqual(["cs.CV/2026-09-10.json", "cs.CV/archive/2017.json"]);

    // A file of a whole budget leaves the others out, the least recently used first.
    await loadDays("cs.CV", [{ date: "2026-09-11", count: PAPER_BUDGET }]);
    await loadDays("cs.CV", [{ date: "2026-09-11", count: PAPER_BUDGET }]);
    await loadArchive("cs.CV", 2017);
    expect(requested.slice(2)).toEqual(["cs.CV/2026-09-11.json", "cs.CV/archive/2017.json"]);
  });

  it("passes the signal that cancels the requests of a period", async () => {
    const signals: (AbortSignal | undefined)[] = [];
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
      signals.push(init?.signal ?? undefined);
      return new Response(JSON.stringify(dayFile("2026-09-10")));
    });
    const controller = new AbortController();
    await loadDays("cs.CV", [{ date: "2026-09-10", count: 1 }], controller.signal);
    await loadArchive("cs.CV", 2017);
    expect(signals).toEqual([controller.signal, undefined]);
  });

  it("loads older days from the search shards of their months, each once", async () => {
    const light = (arxiv_id: string, announced: string) =>
      makePaper({ arxiv_id, announced, light: `cs.CV/${announced}.json` });
    const requested = serve({
      "cs.CV/search/2026-09.json": {
        schema_version: 1,
        papers: [light("a", "2026-09-30"), light("b", "2026-09-29"), light("c", "2026-09-01")],
      },
      "cs.CV/search/2026-08.json": { schema_version: 1, papers: [light("d", "2026-08-31")] },
    });
    const days = [
      { date: "2026-09-30", count: 1 },
      { date: "2026-09-01", count: 1 },
      { date: "2026-08-31", count: 1 },
    ];

    const { papers, missing } = await loadLightDays("cs.CV", days);

    // The days asked for only: a shard holds the whole month.
    expect(papers.map((paper) => paper.arxiv_id)).toEqual(["a", "c", "d"]);
    expect(missing).toEqual([]);
    await loadLightDays("cs.CV", days.slice(0, 1));
    expect(requested).toEqual(["cs.CV/search/2026-09.json", "cs.CV/search/2026-08.json"]);
  });

  it("says which days could not be loaded, and asks for their months again", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    serve(
      { "cs.CV/search/2026-08.json": { schema_version: 2, papers: [] } },
      {
        "cs.CV/search/2026-09.json": 500,
      },
    );
    const days = [
      { date: "2026-09-30", count: 1 },
      { date: "2026-08-31", count: 1 },
    ];

    await expect(loadLightDays("cs.CV", days)).resolves.toEqual({
      papers: [],
      missing: ["2026-09-30", "2026-08-31"],
    });
    expect(warn).toHaveBeenCalledTimes(2);
    const requested = serve({
      "cs.CV/search/2026-09.json": { schema_version: 1, papers: [] },
      "cs.CV/search/2026-08.json": { schema_version: 1, papers: [] },
    });
    await expect(loadLightDays("cs.CV", days)).resolves.toEqual({ papers: [], missing: [] });
    expect(requested).toHaveLength(2);
  });

  it("finds a shared folder's papers by their ids, asking each file only for those left (UX-46)", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const paper = (arxiv_id: string) => makePaper({ arxiv_id });
    const requested = serve({
      // Announced the month after its id's.
      "cs.CV/search/2026-10.json": { schema_version: 1, papers: [paper("2609.11111")] },
      "cs.CV/search/2026-09.json": { schema_version: 1, papers: [paper("2609.22222")] },
      "cs.CV/archive/2017.json": { schema_version: 1, papers: [paper("1706.03762")] },
      "cs.CV/top-recent.json": { schema_version: 1, papers: [paper("2604.33333")] },
    });
    const holding = {
      days: [
        { date: "2026-10-15", count: 1 },
        { date: "2026-09-01", count: 1 },
      ],
      archiveYears: [2017, 2018],
      topRecent: true,
    };
    const ids = ["2604.33333", "2609.11111", "1706.03762", "2609.22222", "1801.00001"];

    const { papers, missing } = await loadPapersById("cs.CV", ids, holding);

    // In the link's order; the shards' months the store holds, the archive's years.
    expect(papers.map(({ arxiv_id }) => arxiv_id)).toEqual(ids.slice(0, 4));
    expect(missing).toEqual(["1801.00001"]);
    expect(requested.sort()).toEqual([
      "cs.CV/archive/2017.json",
      "cs.CV/archive/2018.json",
      "cs.CV/search/2026-09.json",
      "cs.CV/search/2026-10.json",
      "cs.CV/top-recent.json",
    ]);
    // Found in the shards alone: nothing else is asked for.
    const again = serve({
      "cs.CV/search/2026-10.json": { schema_version: 1, papers: [paper("2609.11111")] },
    });
    forgetLoaded();
    await expect(
      loadPapersById("cs.CV", ["2609.11111"], { ...holding, days: holding.days.slice(0, 1) }),
    ).resolves.toEqual({ papers: [paper("2609.11111")], missing: [] });
    expect(again).toEqual(["cs.CV/search/2026-10.json"]);
    expect(warn).toHaveBeenCalled();
  });

  it("loads a search shard's paper whole from its day file", async () => {
    const whole = makePaper({ arxiv_id: "a", announced: "2026-09-30", abstract: "The abstract." });
    serve({ "cs.CV/2026-09-30.json": { schema_version: 1, papers: [whole] } });
    const light = makePaper({
      arxiv_id: "a",
      announced: "2026-09-30",
      light: "cs.CV/2026-09-30.json",
    });

    await expect(loadWholePaper(light)).resolves.toEqual(whole);
    // Loaded whole already, or gone from its day file: the record as given.
    await expect(loadWholePaper(whole)).resolves.toBe(whole);
    const gone = { ...light, arxiv_id: "b" };
    await expect(loadWholePaper(gone)).resolves.toBe(gone);
  });

  it("loads a shard of citation counts, which may not exist", async () => {
    const file = {
      schema_version: 1,
      source: "Semantic Scholar",
      generated_at: "x",
      counts: { a: 1 },
    };
    serve({ "cs.CV/citations/2026-09.json": file });
    await expect(loadCitationShard("cs.CV", "2026-09")).resolves.toEqual(file);
    serve({});
    await expect(loadCitationShard("cs.CV", "2026-09")).resolves.toBeNull();
    serve({}, { "cs.CV/citations/2019.json": 503 });
    await expect(loadCitationShard("cs.CV", "2019")).rejects.toThrow(
      "Could not load citation counts (HTTP 503)",
    );
  });
});
