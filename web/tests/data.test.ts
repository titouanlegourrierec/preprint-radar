import { afterEach, describe, expect, it, vi } from "vitest";
import { loadArchive, loadCitations, loadDays, loadIndex } from "../src/data";
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

afterEach(() => vi.unstubAllGlobals());

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

  it("loads citation counts, which may not exist yet", async () => {
    const file = {
      schema_version: 1,
      source: "Semantic Scholar",
      generated_at: "x",
      counts: { a: 1 },
    };
    serve({ "cs.CV/citations.json": file });
    await expect(loadCitations("cs.CV")).resolves.toEqual(file);
    serve({});
    await expect(loadCitations("cs.CV")).resolves.toBeNull();
    serve({}, { "cs.CV/citations.json": 503 });
    await expect(loadCitations("cs.CV")).rejects.toThrow(
      "Could not load citation counts (HTTP 503)",
    );
  });
});
