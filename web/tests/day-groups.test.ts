import { describe, expect, it } from "vitest";
import { papersPerDay } from "../src/day-groups";
import type { SearchResult } from "../src/search";
import { makePaper } from "./fixtures";

function result(arxivId: string, announced: string): SearchResult {
  return { paper: makePaper({ arxiv_id: arxivId, announced }), score: 0, highlights: [] };
}

describe("papersPerDay", () => {
  it("counts results per day, in result order", () => {
    const counts = papersPerDay([
      result("2609.1", "2026-09-25"),
      result("2609.2", "2026-09-25"),
      result("2609.3", "2026-09-24"),
    ]);

    expect([...counts]).toEqual([
      ["2026-09-25", 2],
      ["2026-09-24", 1],
    ]);
  });

  it("is empty without results", () => {
    expect(papersPerDay([]).size).toBe(0);
  });
});
