import { describe, expect, it } from "vitest";
import { dayGroups } from "../src/day-groups";
import type { SearchResult } from "../src/search";
import { makePaper } from "./fixtures";

function result(arxivId: string, announced: string): SearchResult {
  return { paper: makePaper({ arxiv_id: arxivId, announced }), score: 0, highlights: [] };
}

describe("dayGroups", () => {
  it("groups consecutive results by day, in result order", () => {
    const groups = dayGroups([
      result("2609.1", "2026-09-25"),
      result("2609.2", "2026-09-25"),
      result("2609.3", "2026-09-24"),
    ]);

    expect(
      groups.map(({ day, entries }) => [day, entries.map(({ paper }) => paper.arxiv_id)]),
    ).toEqual([
      ["2026-09-25", ["2609.1", "2609.2"]],
      ["2026-09-24", ["2609.3"]],
    ]);
  });

  it("is empty without results", () => {
    expect(dayGroups([])).toEqual([]);
  });
});
