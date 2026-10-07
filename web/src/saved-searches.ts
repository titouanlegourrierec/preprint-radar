/**
 * Searches saved in this browser, watched for new papers: a topic, an author, a lab. A
 * saved search is the query and filters of a view, as the URL writes them, so that it reads
 * back with {@link readState} and works on any period.
 */
import type { SearchFilters } from "./search";
import { DEFAULT_STATE, readState, writeState } from "./url-state";
import { venueLabel } from "./venues";

export const SAVED_SEARCHES_KEY = "preprint-radar:saved-searches";

export interface SavedSearch {
  /** What the search is, as shown: its words and filters. */
  name: string;
  /** Query string of its words and filters (`?q=gaussian&at=MIT`). */
  search: string;
}

/** The words and filters to search again. */
export interface SearchOf {
  query: string;
  filters: SearchFilters;
}

/** The search of a view: its words and filters, without its period, view or sort. */
export function savedSearch({ query, filters }: SearchOf): SavedSearch | null {
  const search = writeState({ ...DEFAULT_STATE, query, filters });
  return search ? { name: searchName({ query, filters }), search } : null;
}

/** The words and filters of a saved search. */
export function searchOf(saved: SavedSearch): SearchOf {
  const { query, filters } = readState(saved.search);
  return { query, filters };
}

/** "gaussian splatting · by Hao Li · at MIT · ECCV 2026". */
export function searchName({ query, filters }: SearchOf): string {
  const { author, affiliation, venue, subject, excludeCrossLists, withCode } = filters;
  return [
    query.trim(),
    author && `by ${author.text}`,
    affiliation && `at ${affiliation.text}`,
    venue && venueLabel(venue),
    subject,
    excludeCrossLists && "no cross-lists",
    withCode && "with code",
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * The saved searches of a stored value or an imported file; entries that are not searches
 * are skipped, and a search is kept once.
 */
export function readSearches(value: unknown): SavedSearch[] {
  if (!Array.isArray(value)) return [];
  const searches = new Map<string, SavedSearch>();
  for (const entry of value) {
    if (typeof entry !== "object" || entry === null) continue;
    const { name, search } = entry as Record<string, unknown>;
    if (typeof name === "string" && typeof search === "string" && search.startsWith("?")) {
      searches.set(search, { name, search });
    }
  }
  return [...searches.values()];
}

export function loadSavedSearches(): SavedSearch[] {
  try {
    return readSearches(JSON.parse(localStorage.getItem(SAVED_SEARCHES_KEY) ?? "[]"));
  } catch {
    return [];
  }
}

/** Store the searches; `false` when the browser refused. */
export function saveSavedSearches(searches: SavedSearch[]): boolean {
  try {
    localStorage.setItem(SAVED_SEARCHES_KEY, JSON.stringify(searches));
    return true;
  } catch {
    return false;
  }
}
