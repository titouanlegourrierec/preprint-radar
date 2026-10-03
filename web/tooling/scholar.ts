import type { ScholarFile } from "../src/types";

/** A paper as a day or archive file holds it, for what the merge reads and writes. */
interface StoredPaper {
  arxiv_id: string;
  venue?: string | null;
  doi?: string | null;
}

/**
 * A day or archive file (JSON text) with what `scholar.json` knows of its papers: the DOI of
 * the published version, and the venue it was published at where the comments name none
 * (the comments, when they name one, are more often right: Semantic Scholar takes papers of
 * the Image Processing ICIP for the Information Photonics one). The store keeps them apart,
 * since `scholar.json` is rewritten every week; the site's records carry them.
 */
export function withScholar(text: string, scholar: ScholarFile | null): string {
  if (scholar === null) return text;
  const file = JSON.parse(text) as { papers: StoredPaper[] };
  for (const paper of file.papers) {
    const record = scholar.papers[paper.arxiv_id];
    if (record === undefined) continue;
    if (record.doi) paper.doi = record.doi;
    if (!paper.venue && record.venue) paper.venue = record.venue;
  }
  return JSON.stringify(file);
}

/** The paths of the day and archive files of a store, under `data/`, from its index. */
export function paperFiles(index: {
  categories: Record<string, { date: string }[]>;
  archives?: Record<string, { year: number }[]>;
}): { category: string; path: string }[] {
  return Object.entries(index.categories).flatMap(([category, days]) => [
    ...days.map(({ date }) => ({ category, path: `${category}/${date}.json` })),
    ...(index.archives?.[category] ?? []).map(({ year }) => ({
      category,
      path: `${category}/archive/${year}.json`,
    })),
  ]);
}
