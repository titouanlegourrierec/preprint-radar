import { searchKey } from "../src/text";
import type { ScholarFile } from "../src/types";

/** A paper as a day or archive file holds it, for what the merge reads and writes. */
interface StoredPaper {
  arxiv_id: string;
  authors?: string[];
  venue?: string | null;
  doi?: string | null;
  author_ids?: (string | null)[];
}

/** Each author name (as a search key) and the one Semantic Scholar id it goes with. */
export type AuthorIds = ReadonlyMap<string, string>;

/**
 * The names that only one person of the store goes by, with that person's Semantic Scholar
 * id: an author the scholar record has no id for is then that person. A name two ids share
 * is left out: its papers without an id could be either's.
 */
export function authorIdsByName(texts: Iterable<string>, scholar: ScholarFile | null): AuthorIds {
  const ids = new Map<string, Set<string>>();
  for (const text of texts) {
    for (const paper of (JSON.parse(text) as { papers: StoredPaper[] }).papers) {
      const known = scholar?.papers[paper.arxiv_id]?.author_ids;
      const authors = paper.authors ?? [];
      if (known?.length !== authors.length) continue;
      for (const [position, author] of authors.entries()) {
        const id = known[position];
        if (!id) continue;
        const key = searchKey(author);
        ids.set(key, (ids.get(key) ?? new Set()).add(id));
      }
    }
  }
  const unique = new Map<string, string>();
  for (const [key, found] of ids) if (found.size === 1) unique.set(key, [...found][0] ?? "");
  return unique;
}

/**
 * A day or archive file (JSON text) with what `scholar.json` knows of its papers: the DOI of
 * the published version, the venue it was published at where the comments name none (the
 * comments, when they name one, are more often right: Semantic Scholar takes papers of the
 * Image Processing ICIP for the Information Photonics one), and its authors' ids, an author
 * without one taking the id of the only person of that name (`byName`). The store keeps
 * them apart, since `scholar.json` is rewritten every week; the site's records carry them.
 */
export function withScholar(
  text: string,
  scholar: ScholarFile | null,
  byName: AuthorIds = new Map(),
): string {
  if (scholar === null) return text;
  const file = JSON.parse(text) as { papers: StoredPaper[] };
  for (const paper of file.papers) {
    const record = scholar.papers[paper.arxiv_id];
    if (record?.doi) paper.doi = record.doi;
    if (!paper.venue && record?.venue) paper.venue = record.venue;
    const authors = paper.authors ?? [];
    const known = record?.author_ids?.length === authors.length ? record.author_ids : null;
    const ids = authors.map(
      (author, position) => known?.[position] || byName.get(searchKey(author)) || null,
    );
    if (ids.some(Boolean)) paper.author_ids = ids;
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
