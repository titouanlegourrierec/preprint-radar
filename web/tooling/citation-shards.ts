import { citationShardPath, type Filed, splitCitations } from "../src/citations";
import type { CitationsFile, StoreIndex } from "../src/types";

/** Reads a JSON file of the store by its path under `data/`; `null` when there is none. */
export type ReadJson = (path: string) => unknown;

/**
 * The citation shards of a store (see `src/citations.ts`), as JSON text by path under
 * `data/`: for each category of the index with a `citations.json`, its counts split by
 * the day and archive files the index lists.
 */
export function citationShardFiles(read: ReadJson): Map<string, string> {
  const files = new Map<string, string>();
  const index = read("index.json") as StoreIndex | null;
  if (index === null) return files;
  for (const [category, days] of Object.entries(index.categories)) {
    const citations = read(`${category}/citations.json`) as CitationsFile | null;
    if (citations === null) continue;
    const paths = [
      ...days.map(({ date }) => `${category}/${date}.json`),
      ...(index.archives?.[category] ?? []).map(({ year }) => `${category}/archive/${year}.json`),
    ];
    const records = paths.flatMap((path) => (read(path) as { papers: Filed[] }).papers);
    for (const [shard, file] of splitCitations(citations, records, days.at(-1)?.date)) {
      files.set(citationShardPath(category, shard), JSON.stringify(file));
    }
  }
  return files;
}
