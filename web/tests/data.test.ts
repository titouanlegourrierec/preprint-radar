import { afterEach, describe, expect, it, vi } from "vitest";
import { forgetLoaded, loadArchive, loadCitationShard, loadDays, loadIndex } from "../src/data";
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
  forgetLoaded();
});

function dayFile(date: string, papers = 1) {
  return {
    schema_version: 1,
    papers: Array.from({ length: papers }, (_, n) => makePaper({ arxiv_id: `${date}.${n}` })),
  };
}

describe("data", () => {
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

    const papers = await loadDays("cs.CV", days);

    expect(papers.map(({ arxiv_id }) => arxiv_id)).toEqual(days.map(({ date }) => date));
    expect(requested).toHaveLength(9);
    await expect(loadDays("cs.CV", [])).resolves.toEqual([]);
  });

  it("fails a period whose day file fails", async () => {
    serve(
      { "cs.CV/2026-09-10.json": { schema_version: 1, papers: [] } },
      { "cs.CV/2026-09-11.json": 500 },
    );
    await expect(
      loadDays("cs.CV", [
        { date: "2026-09-10", count: 0 },
        { date: "2026-09-11", count: 0 },
      ]),
    ).rejects.toThrow("Could not load cs.CV/2026-09-11.json (HTTP 500)");
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
