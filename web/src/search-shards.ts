/**
 * Search shards (PERF-1): the papers of the day files by month, whole but for their
 * abstract and comments, which are most of a record (134 bytes a paper gzipped instead of
 * 735). A period loads its latest days whole, within `PAPER_BUDGET`; its older days come
 * from these shards, so that months of titles, authors, affiliations and venues are
 * searched, and a card loads its day file for its abstract when opened. The build writes
 * them (`tooling/search-shards.ts`): they are never in `data/`.
 */
import { codeUrl } from "./code";
import type { Paper } from "./types";

/** Path of the search shard of a month ("2026-09") under `data/`. */
export function searchShardPath(category: string, month: string): string {
  return `${category}/search/${month}.json`;
}

/** Path of the day file that holds a paper of a category whole, under `data/`. */
export function dayFilePath(category: string, day: string): string {
  return `${category}/${day}.json`;
}

/** The months ("2026-09") of some days, newest first, once each. */
export function monthsOf(days: Iterable<{ date: string }>): string[] {
  return [...new Set([...days].map(({ date }) => date.slice(0, 7)))].sort().reverse();
}

/**
 * A paper as its search shard holds it: without its abstract and comments, but the code
 * they link (`code_url`, which `codeUrl` reads then), and the day file that holds it whole
 * (`light`). What the app does not read goes too (`provenance`, `extractor`).
 */
export function lightRecord(paper: Paper, dayFile: string): Paper {
  const {
    abstract: _abstract,
    comments: _comments,
    provenance: _provenance,
    extractor: _extractor,
    ...kept
  } = paper;
  return {
    ...kept,
    abstract: null,
    comments: null,
    code_url: codeUrl(paper),
    light: dayFile,
  };
}

/** `<category>/search/<YYYY-MM>.json`: the light records of a month's day files. */
export interface SearchShardFile {
  schema_version: number;
  category: string;
  month: string;
  papers: Paper[];
}
