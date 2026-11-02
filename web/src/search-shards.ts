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

/**
 * Path of a paper file's light version (WEB-5): "cs.CV/2026-09-25.json" is
 * "cs.CV/light/2026-09-25.json", "cs.CV/archive/2017.json" "cs.CV/light/archive/2017.json".
 * Its records are the search shards' (`lightRecord`); the build writes it.
 */
export function lightPath(path: string): string {
  return path.replace("/", "/light/");
}

/** Path of the abstracts and comments of a paper file's records, beside its light version. */
export function abstractsPath(path: string): string {
  return path.replace("/", "/abstracts/");
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

/**
 * `<category>/abstracts/...`: what a paper file's light version leaves out, by arXiv id: each
 * paper's abstract and comments (WEB-5), `null` where it has none.
 */
export interface AbstractsFile {
  schema_version: number;
  abstracts: Record<string, [string | null, string | null]>;
}

/** A light record with its abstract and comments back, as its paper file holds it. */
export function withText(paper: Paper, text: [string | null, string | null] | undefined): Paper {
  const { light: _light, code_url: _codeUrl, ...whole } = paper;
  const [abstract, comments] = text ?? [null, null];
  return { ...whole, abstract, comments };
}
