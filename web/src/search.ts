import MiniSearch, { type SearchResult as MiniSearchResult } from "minisearch";
import { paperInstitutions } from "./institutions";
import { fold } from "./text";
import type { Paper } from "./types";

export type SortOrder = "relevance" | "newest";

export interface SearchFilters {
  excludeCrossLists: boolean;
  author: string | null;
  affiliation: string | null;
  subject: string | null;
  /** A venue as detected in the comments (e.g. "ECCV 2026"), or {@link ANY_VENUE}. */
  venue: string | null;
}

/** Venue filter value for papers accepted anywhere. */
export const ANY_VENUE = "*";

export const NO_FILTERS: SearchFilters = {
  excludeCrossLists: false,
  author: null,
  affiliation: null,
  subject: null,
  venue: null,
};

export interface ParsedQuery {
  /** Free text, matched with prefix and fuzzy search. */
  text: string;
  /** `"quoted phrases"` that must appear verbatim (accent- and case-insensitive). */
  phrases: string[];
  /** `-words` that must not appear. */
  excluded: string[];
}

export interface SearchResult {
  paper: Paper;
  score: number;
  /** Words to highlight in the rendered paper. */
  highlights: string[];
}

export interface FacetCount {
  value: string;
  count: number;
}

const STOP_WORDS = new Set(
  "a an and are as at be by for from in into is of on or the to via with without".split(" "),
);

const FIELD_BOOSTS = {
  title: 3,
  authors: 2,
  affiliations: 1.5,
  venue: 1.5,
  abstract: 1,
  comments: 0.5,
};
const SEARCHED_FIELDS = Object.keys(FIELD_BOOSTS);

export function parseQuery(raw: string): ParsedQuery {
  const phrases: string[] = [];
  const excluded: string[] = [];
  const text = raw
    .replace(/"([^"]+)"/g, (_, phrase: string) => {
      if (phrase.trim()) phrases.push(fold(phrase.trim()));
      return " ";
    })
    .replace(/(^|\s)-(\S+)/g, (_, space: string, word: string) => {
      excluded.push(fold(word));
      return space;
    })
    .replace(/\s+/g, " ")
    .trim();
  return { text, phrases, excluded };
}

function processTerm(term: string): string | null {
  const folded = fold(term);
  return STOP_WORDS.has(folded) ? null : folded;
}

function fieldValue(paper: Paper, field: string): string {
  switch (field) {
    case "authors":
      return paper.authors.join(" ");
    case "affiliations":
      // The institutions' names too, so that "Carnegie Mellon" finds "CMU".
      return [...new Set([...(paper.affiliations ?? []), ...paperInstitutions(paper)])].join(" ");
    case "title":
      return paper.title;
    case "abstract":
      return paper.abstract ?? "";
    case "comments":
      return paper.comments ?? "";
    case "venue":
      return paper.venue ?? "";
    default:
      return "";
  }
}

function searchableText(paper: Paper): string {
  return fold(`${paper.title} ${paper.abstract ?? ""} ${paper.comments ?? ""}`);
}

function newestFirst(a: SearchResult, b: SearchResult): number {
  return (
    b.paper.announced.localeCompare(a.paper.announced) ||
    b.paper.arxiv_id.localeCompare(a.paper.arxiv_id)
  );
}

/** Full-text index over a set of papers, with structured filters. */
export class PaperIndex {
  private readonly index: MiniSearch<Paper>;
  private readonly papers: Map<string, Paper>;

  constructor(papers: Paper[]) {
    // A paper cross-listed in several loaded days would otherwise be indexed twice.
    this.papers = new Map(papers.map((paper) => [paper.arxiv_id, paper]));
    this.index = new MiniSearch<Paper>({
      idField: "arxiv_id",
      fields: SEARCHED_FIELDS,
      extractField: (paper, field) =>
        field === "arxiv_id" ? paper.arxiv_id : fieldValue(paper, field),
      processTerm,
      searchOptions: {
        boost: FIELD_BOOSTS,
        combineWith: "AND",
        prefix: true,
        fuzzy: (term) => (term.length >= 5 ? 0.2 : false),
      },
    });
    this.index.addAll([...this.papers.values()]);
  }

  get size(): number {
    return this.papers.size;
  }

  /** Every indexed paper, in no particular order. */
  all(): Paper[] {
    return [...this.papers.values()];
  }

  search(rawQuery: string, filters: SearchFilters, sort: SortOrder): SearchResult[] {
    const query = parseQuery(rawQuery);
    const results = query.text
      ? this.index.search(query.text).flatMap((hit) => this.toResult(hit))
      : [...this.papers.values()].map((paper) => ({ paper, score: 0, highlights: [] }));

    const filtered = results.filter(
      ({ paper }) => matchesFilters(paper, filters) && matchesQueryConstraints(paper, query),
    );
    const extraHighlights = [...query.phrases, ...filterHighlights(filters)];
    for (const result of filtered) {
      result.highlights.push(...extraHighlights);
    }
    return filtered.sort(
      sort === "relevance" && query.text
        ? (a, b) => b.score - a.score || newestFirst(a, b)
        : newestFirst,
    );
  }

  private toResult(hit: MiniSearchResult): SearchResult[] {
    const paper = this.papers.get(String(hit.id));
    return paper ? [{ paper, score: hit.score, highlights: [...hit.terms] }] : [];
  }
}

function containsFolded(values: readonly string[], needle: string | null): boolean {
  if (!needle?.trim()) return true;
  const folded = fold(needle.trim());
  return values.some((value) => fold(value).includes(folded));
}

/**
 * Author and affiliation filters match any value containing the text, ignoring case and
 * accents, so that "kaist" matches "KAIST, Daejeon" and "perez" matches "Lozano-Pérez".
 * Affiliations also match by institution, so that a graph node's name ("Carnegie Mellon
 * University") finds the papers written "CMU".
 */
export function matchesFilters(paper: Paper, filters: SearchFilters): boolean {
  return (
    !(filters.excludeCrossLists && paper.cross_list_from !== null) &&
    containsFolded(paper.authors, filters.author) &&
    // Institutions are only named when an affiliation filter needs them.
    (!filters.affiliation?.trim() ||
      containsFolded(
        [...(paper.affiliations ?? []), ...paperInstitutions(paper)],
        filters.affiliation,
      )) &&
    (filters.subject === null || paper.primary_subject === filters.subject) &&
    (filters.venue === null ||
      (filters.venue === ANY_VENUE ? Boolean(paper.venue) : paper.venue === filters.venue))
  );
}

function filterHighlights(filters: SearchFilters): string[] {
  return [filters.author, filters.affiliation].flatMap((value) =>
    value
      ? fold(value)
          .split(/\s+/)
          .filter((word) => word && !STOP_WORDS.has(word))
      : [],
  );
}

function matchesQueryConstraints(paper: Paper, query: ParsedQuery): boolean {
  if (query.phrases.length === 0 && query.excluded.length === 0) return true;
  const text = searchableText(paper);
  const words = new Set(text.split(/[^\p{L}\p{N}]+/u));
  return (
    query.phrases.every((phrase) => text.includes(phrase)) &&
    !query.excluded.some((word) => words.has(word))
  );
}

/** Most frequent values of a multi-valued field among papers. */
export function valueCounts(
  papers: Iterable<Paper>,
  values: (paper: Paper) => Iterable<string>,
  limit: number,
): FacetCount[] {
  const counts = new Map<string, number>();
  for (const paper of papers) {
    for (const value of new Set(values(paper))) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
  }
  return [...counts]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
    .slice(0, limit);
}

/** The same values sorted alphabetically, ignoring case and accents. */
export function alphabetical(values: readonly FacetCount[]): FacetCount[] {
  return [...values].sort((a, b) => fold(a.value).localeCompare(fold(b.value)));
}

/** Most frequent values of a multi-valued field among search results. */
export function facetCounts(
  results: SearchResult[],
  values: (paper: Paper) => Iterable<string>,
  limit: number,
): FacetCount[] {
  return valueCounts(
    results.map(({ paper }) => paper),
    values,
    limit,
  );
}
