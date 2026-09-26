import type { SearchResult } from "./search";

export interface DayGroup {
  day: string;
  entries: SearchResult[];
}

/**
 * Consecutive results grouped by announcement day, in result order.
 *
 * Used for the foldable day sections of the paper list, which only make sense when
 * the results are in announcement order (no search words, or sorted by newest).
 */
export function dayGroups(results: readonly SearchResult[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const entry of results) {
    const group = groups.at(-1);
    if (group && group.day === entry.paper.announced) group.entries.push(entry);
    else groups.push({ day: entry.paper.announced, entries: [entry] });
  }
  return groups;
}
