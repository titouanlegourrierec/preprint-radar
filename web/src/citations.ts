/**
 * Citation counts, in shards. `citations.json` holds the count of every stored paper (about
 * 26,000, 125 KB gzipped), while a page shows a few thousand: the build splits it by where
 * each paper is filed (`tooling/citation-shards.ts`), and a page loads the shards of the
 * papers it shows.
 */
import type { CitationsFile } from "./types";

/** What a paper is filed under: its identifier and announcement day. */
export interface Filed {
  arxiv_id: string;
  announced: string;
}

/**
 * The shard of a paper's count: the month of its announcement ("2026-09") for a paper of
 * the day files, else the year of its first appearance ("2019"), as the archive files it.
 * `oldestDay` is the oldest day file of the category, from the index.
 */
export function citationShard(announced: string, oldestDay: string | undefined): string {
  return oldestDay !== undefined && announced >= oldestDay
    ? announced.slice(0, 7)
    : announced.slice(0, 4);
}

/** Path of a shard under `data/`. */
export function citationShardPath(category: string, shard: string): string {
  return `${category}/citations/${shard}.json`;
}

/** The shards that hold the counts of these papers, sorted. */
export function shardsOf(papers: Iterable<Filed>, oldestDay: string | undefined): string[] {
  const shards = new Set<string>();
  for (const paper of papers) shards.add(citationShard(paper.announced, oldestDay));
  return [...shards].sort();
}

/**
 * The shards of a citations file: each count goes to the shard of every record of its
 * paper (a paper both in a day file and in the archive may be filed twice), and the counts
 * of papers no longer stored are left out. Every shard keeps the file's date and source.
 */
export function splitCitations(
  file: CitationsFile,
  records: Iterable<Filed>,
  oldestDay: string | undefined,
): Map<string, CitationsFile> {
  const shards = new Map<string, CitationsFile>();
  for (const { arxiv_id, announced } of records) {
    const count = file.counts[arxiv_id];
    if (count === undefined) continue;
    const shard = citationShard(announced, oldestDay);
    let part = shards.get(shard);
    if (part === undefined) {
      part = { ...file, counts: {} };
      shards.set(shard, part);
    }
    part.counts[arxiv_id] = count;
  }
  return shards;
}
