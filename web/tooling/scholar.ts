import type { CodeFile, CodeStats, ScholarFile } from "../src/types";
import { mergeCode } from "./code";

/** A paper as a day or archive file holds it, for what the merge reads and writes. */
export interface StoredPaper {
  arxiv_id: string;
  authors?: string[];
  venue?: string | null;
  doi?: string | null;
  author_ids?: (string | null)[];
  abstract?: string | null;
  comments?: string | null;
  code?: CodeStats;
}

/**
 * A day or archive file (JSON text) with what only the site's records hold, which the store
 * keeps apart since it is rewritten every week: what `scholar.json` knows of its papers
 * ({@link mergeScholar}), and how popular their code is (`code.json`, `mergeCode`).
 */
export function withSiteFields(
  text: string,
  scholar: ScholarFile | null,
  code: CodeFile | null = null,
): string {
  if (scholar === null && code === null) return text;
  const file = JSON.parse(text) as { papers: StoredPaper[] };
  if (scholar !== null) mergeScholar(file.papers, scholar);
  if (code !== null) mergeCode(file.papers, code);
  return JSON.stringify(file);
}

/**
 * What `scholar.json` knows of the papers, in place: the DOI of the published version, and
 * the venue it was published at where the comments name none (the comments, when they name
 * one, are more often right: Semantic Scholar takes papers of the Image Processing ICIP for
 * the Information Photonics one), and its authors' ids, which tell the graph when a name is
 * several people's. The feeds read it too (`tooling/feeds.ts`).
 */
export function mergeScholar(papers: StoredPaper[], scholar: ScholarFile): void {
  for (const paper of papers) {
    const record = scholar.papers[paper.arxiv_id];
    if (record === undefined) continue;
    if (record.doi) paper.doi = record.doi;
    if (!paper.venue && record.venue) paper.venue = record.venue;
    if (record.author_ids?.length === paper.authors?.length && record.author_ids?.some(Boolean)) {
      paper.author_ids = record.author_ids;
    }
  }
}

/**
 * The paths of the day and archive files of a store, and of its most cited papers of the
 * last 12 months, under `data/`, from its index.
 */
export function paperFiles(index: {
  categories: Record<string, { date: string }[]>;
  archives?: Record<string, { year: number }[]>;
  top_recent?: Record<string, unknown>;
}): { category: string; path: string }[] {
  return Object.entries(index.categories).flatMap(([category, days]) => [
    ...days.map(({ date }) => ({ category, path: `${category}/${date}.json` })),
    ...(index.archives?.[category] ?? []).map(({ year }) => ({
      category,
      path: `${category}/archive/${year}.json`,
    })),
    ...(index.top_recent?.[category] ? [{ category, path: `${category}/top-recent.json` }] : []),
  ]);
}
