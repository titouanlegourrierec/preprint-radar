import type { SearchResult } from "./search";

/**
 * Number of results per announcement day, in result order.
 *
 * Used for the day headings of the paper list, which only make sense when the results
 * are in announcement order (no search words, or sorted by newest).
 */
export function papersPerDay(results: readonly SearchResult[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const { paper } of results) {
    counts.set(paper.announced, (counts.get(paper.announced) ?? 0) + 1);
  }
  return counts;
}
