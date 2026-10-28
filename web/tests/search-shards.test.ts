import { describe, expect, it } from "vitest";
import {
  dayFilePath,
  lightRecord,
  monthsOf,
  type SearchShardFile,
  searchShardPath,
} from "../src/search-shards";
import type { CodeFile, ScholarFile } from "../src/types";
import { searchShardFiles } from "../tooling/search-shards";
import { makePaper } from "./fixtures";

describe("search shard paths", () => {
  it("names a month's shard and a day file", () => {
    expect(searchShardPath("cs.CV", "2026-09")).toBe("cs.CV/search/2026-09.json");
    expect(dayFilePath("cs.CV", "2026-09-25")).toBe("cs.CV/2026-09-25.json");
  });

  it("lists the months of some days once, newest first", () => {
    const days = [{ date: "2026-10-02" }, { date: "2026-09-30" }, { date: "2026-10-01" }];
    expect(monthsOf(days)).toEqual(["2026-10", "2026-09"]);
    expect(monthsOf([])).toEqual([]);
  });
});

describe("lightRecord", () => {
  it("keeps all but the abstract and comments, with the code they link and the day file", () => {
    const paper = makePaper({
      arxiv_id: "2609.00001",
      abstract: "Code is available at https://github.com/example/splat.",
      comments: "CVPR 2026",
      venue: "CVPR 2026",
      affiliations: ["MIT"],
      extractor: 9,
      provenance: { affiliations: { source: "html", at: "2026-09-25" } },
    });

    const light = lightRecord(paper, "cs.CV/2026-09-25.json");

    expect(light).toMatchObject({
      arxiv_id: "2609.00001",
      title: paper.title,
      venue: "CVPR 2026",
      affiliations: ["MIT"],
      abstract: null,
      comments: null,
      code_url: "https://github.com/example/splat",
      light: "cs.CV/2026-09-25.json",
    });
    expect(light).not.toHaveProperty("extractor");
    expect(light).not.toHaveProperty("provenance");
    expect(lightRecord(makePaper({ arxiv_id: "2609.00002" }), "x").code_url).toBeNull();
  });
});

describe("searchShardFiles", () => {
  const scholar: ScholarFile = {
    schema_version: 1,
    category: "cs.CV",
    generated_at: "2026-10-04T06:00:00+00:00",
    source: "Semantic Scholar",
    papers: { "2609.00001": { doi: "10.1000/example", venue: "ICCV 2025" } },
  };
  const code: CodeFile = {
    schema_version: 1,
    category: "cs.CV",
    generated_at: "2026-10-04T06:00:00+00:00",
    since: null,
    source: "GitHub, Hugging Face",
    papers: { "2610.00002": { url: "https://github.com/example/tool", stars: 12 } },
  };
  const store: Record<string, unknown> = {
    "index.json": {
      schema_version: 1,
      generated_at: "2026-10-02T08:00:00+00:00",
      categories: {
        "cs.CV": [
          { date: "2026-10-01", count: 1 },
          { date: "2026-09-30", count: 1 },
          { date: "2026-09-29", count: 0 },
        ],
      },
    },
    "cs.CV/scholar.json": scholar,
    "cs.CV/code.json": code,
    "cs.CV/countries.json": {
      schema_version: 1,
      generated_at: "2026-10-04T06:00:00+00:00",
      source: "OpenAlex",
      institutions: { "0abcde001": "FR" },
    },
    "cs.CV/2026-10-01.json": {
      schema_version: 1,
      papers: [
        makePaper({
          arxiv_id: "2610.00002",
          announced: "2026-10-01",
          abstract: "Code: https://github.com/example/tool",
        }),
      ],
    },
    "cs.CV/2026-09-30.json": {
      schema_version: 1,
      papers: [
        makePaper({
          arxiv_id: "2609.00001",
          announced: "2026-09-30",
          abstract: "A.",
          affiliations: ["Inria"],
          institutions: ["Inria"],
          institution_ids: ["0abcde001"],
        }),
      ],
    },
    // A day the index lists whose file is missing gives nothing.
  };
  const read = (path: string) => store[path] ?? null;

  it("writes a shard per month of the day files, records as the site gets them", () => {
    const files = searchShardFiles(read);

    expect([...files.keys()].sort()).toEqual([
      "cs.CV/search/2026-09.json",
      "cs.CV/search/2026-10.json",
    ]);
    const september = JSON.parse(files.get("cs.CV/search/2026-09.json") ?? "") as SearchShardFile;
    expect(september).toMatchObject({ schema_version: 1, category: "cs.CV", month: "2026-09" });
    expect(september.papers).toEqual([
      expect.objectContaining({
        arxiv_id: "2609.00001",
        doi: "10.1000/example",
        venue: "ICCV 2025",
        // The older days of a period filter on countries too (PROD-22).
        countries: ["FR"],
        abstract: null,
        light: "cs.CV/2026-09-30.json",
      }),
    ]);
    const october = JSON.parse(files.get("cs.CV/search/2026-10.json") ?? "") as SearchShardFile;
    expect(october.papers[0]).toMatchObject({
      code: { stars: 12 },
      code_url: "https://github.com/example/tool",
    });
  });

  it("writes nothing without an index, and needs no scholar or code file", () => {
    expect(searchShardFiles(() => null).size).toBe(0);
    const bare = (path: string) =>
      path.endsWith("scholar.json") || path.endsWith("code.json") ? null : read(path);
    expect(searchShardFiles(bare).size).toBe(2);
  });
});
