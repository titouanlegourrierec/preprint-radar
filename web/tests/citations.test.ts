import { describe, expect, it } from "vitest";
import { citationShard, citationShardPath, shardsOf, splitCitations } from "../src/citations";
import { citationShardFiles } from "../tooling/citation-shards";

const citations = {
  schema_version: 1,
  category: "cs.CV",
  generated_at: "2026-09-30T13:19:35+00:00",
  source: "Semantic Scholar",
  counts: { "2609.00001": 3, "2610.00002": 0, "1706.03762": 150000, "2509.12345": 40 },
};

describe("citation shards", () => {
  it("files a paper by month in the day files, by year before them", () => {
    expect(citationShard("2026-09-24", "2026-09-01")).toBe("2026-09");
    expect(citationShard("2026-09-01", "2026-09-01")).toBe("2026-09");
    expect(citationShard("2025-08-31", "2026-09-01")).toBe("2025");
    expect(citationShard("2017-06-12", undefined)).toBe("2017");
    expect(citationShardPath("cs.CV", "2017")).toBe("cs.CV/citations/2017.json");
  });

  it("names the shards of the papers shown, once each", () => {
    const papers = [
      { arxiv_id: "a", announced: "2026-10-01" },
      { arxiv_id: "b", announced: "2026-09-24" },
      { arxiv_id: "c", announced: "2026-09-25" },
      { arxiv_id: "d", announced: "2017-06-12" },
    ];
    expect(shardsOf(papers, "2026-09-01")).toEqual(["2017", "2026-09", "2026-10"]);
    expect(shardsOf([], "2026-09-01")).toEqual([]);
  });

  it("splits the counts by shard, dated, without papers no longer stored", () => {
    const shards = splitCitations(
      citations,
      [
        { arxiv_id: "2609.00001", announced: "2026-09-24" },
        { arxiv_id: "2610.00002", announced: "2026-10-01" },
        { arxiv_id: "1706.03762", announced: "2017-06-12" },
        // An old paper cross-listed lately: in a day file and in the archive.
        { arxiv_id: "2509.12345", announced: "2026-09-25" },
        { arxiv_id: "2509.12345", announced: "2025-09-15" },
        { arxiv_id: "2609.99999", announced: "2026-09-25" },
      ],
      "2026-09-01",
    );
    expect([...shards.keys()].sort()).toEqual(["2017", "2025", "2026-09", "2026-10"]);
    expect(shards.get("2026-09")).toEqual({
      ...citations,
      counts: { "2609.00001": 3, "2509.12345": 40 },
    });
    expect(shards.get("2025")?.counts).toEqual({ "2509.12345": 40 });
    expect(shards.get("2026-10")?.counts).toEqual({ "2610.00002": 0 });
  });
});

describe("citation gains in the shards", () => {
  const gains = {
    schema_version: 1,
    category: "cs.CV",
    since: "2026-09-27T05:41:00+00:00",
    generated_at: "2026-10-04T05:41:00+00:00",
    source: "Semantic Scholar",
    gains: { "1706.03762": 120, "2609.99999": 1 },
  };

  it("go with their papers, each shard saying the days they span", () => {
    const shards = splitCitations(
      citations,
      [
        { arxiv_id: "2609.00001", announced: "2026-09-24" },
        { arxiv_id: "1706.03762", announced: "2017-06-12" },
      ],
      "2026-09-01",
      gains,
    );
    expect(shards.get("2017")?.gains).toEqual({
      since: gains.since,
      to: gains.generated_at,
      counts: { "1706.03762": 120 },
    });
    // A shard without gains still says that gains are known: none there.
    expect(shards.get("2026-09")?.gains).toEqual({
      since: gains.since,
      to: gains.generated_at,
      counts: {},
    });
  });

  it("are absent without a gains file", () => {
    const shards = splitCitations(
      citations,
      [{ arxiv_id: "1706.03762", announced: "2017-06-12" }],
      "2026-09-01",
    );
    expect(shards.get("2017")?.gains).toBeUndefined();
  });
});

describe("citationShardFiles", () => {
  const read = (files: Record<string, unknown>) => (path: string) => files[path] ?? null;

  it("splits each category's counts by the files of its index", () => {
    const files = citationShardFiles(
      read({
        "index.json": {
          schema_version: 1,
          generated_at: "x",
          categories: {
            "cs.CV": [{ date: "2026-09-24", count: 1 }],
            "cs.RO": [{ date: "2026-09-24", count: 0 }],
          },
          archives: { "cs.CV": [{ year: 2017, count: 1 }] },
        },
        "cs.CV/2026-09-24.json": {
          papers: [{ arxiv_id: "2609.00001", announced: "2026-09-24" }],
        },
        "cs.CV/archive/2017.json": {
          papers: [{ arxiv_id: "1706.03762", announced: "2017-06-12" }],
        },
        "cs.CV/citations.json": citations,
        "cs.CV/citation-gains.json": {
          since: "2026-09-27T05:41:00+00:00",
          generated_at: "2026-10-04T05:41:00+00:00",
          gains: { "1706.03762": 120 },
        },
      }),
    );
    expect([...files.keys()].sort()).toEqual([
      "cs.CV/citations/2017.json",
      "cs.CV/citations/2026-09.json",
    ]);
    expect(JSON.parse(files.get("cs.CV/citations/2017.json") ?? "")).toMatchObject({
      generated_at: citations.generated_at,
      counts: { "1706.03762": 150000 },
      gains: { counts: { "1706.03762": 120 } },
    });
  });

  it("gives nothing for a store without an index", () => {
    expect(citationShardFiles(read({})).size).toBe(0);
  });
});
