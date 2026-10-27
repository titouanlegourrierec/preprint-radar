/**
 * A search of every stored paper (PROD-21), the period aside: each file of the store read
 * in turn through a cheap test of the words and filters, its papers kept only while they
 * are tested, so that memory holds what passes, not the store. Loaded with the first such
 * search: the landing page does without it (PERF-15).
 */
import { readStoreFile, SchemaVersionError, type StoreHolding } from "./data";
import { PAPER_BUDGET } from "./period";
import {
  activeFilterCount,
  arxivIdOf,
  foldedText,
  MIN_FUZZY_LENGTH,
  matchesFilters,
  paperTerms,
  parseQuery,
  type SearchFilters,
  termsOf,
} from "./search";
import type { Paper } from "./types";

/**
 * Whether two words are one edit apart at most (Levenshtein: a letter changed, added or
 * left out), the typo the index allows in a word of {@link MIN_FUZZY_LENGTH} letters.
 */
function withinOneEdit(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  let same = 0;
  while (same < a.length && a[same] === b[same]) same++;
  if (a.length === b.length) return a.slice(same + 1) === b.slice(same + 1);
  return a.length > b.length
    ? a.slice(same + 1) === b.slice(same)
    : a.slice(same) === b.slice(same + 1);
}

/**
 * Whether a paper may hold a word of the query as the index matches it: its folded text
 * holds the word, which a word it starts or equals holds; or, for a word a typo may match,
 * one of the word's halves, which one edit leaves whole ("detecton" holds "dete" of
 * "detection"), and then one of the paper's words is one edit from it, as its index would
 * have them (`words`, built once a paper).
 */
function mayHold(term: string, text: string, words: () => string[]): boolean {
  if (text.includes(term)) return true;
  if (term.length < MIN_FUZZY_LENGTH) return false;
  const half = Math.floor(term.length / 2);
  if (!(text.includes(term.slice(0, half)) || text.includes(term.slice(half)))) return false;
  return words().some((word) => withinOneEdit(word, term));
}

/**
 * A test of every stored paper for a search of them all (PROD-21), too many to index: true
 * of every paper `PaperIndex.search` finds, and cheap, about 5 µs a paper against
 * 175 µs to index it. A paper passes the filters, and may hold each word of the query and
 * of its phrases, and every word of an alternative of each `OR` ({@link mayHold}); the
 * index then ranks those that pass, and leaves out the few it does not match (a word
 * inside another, exclusions, words out of order). A pasted arXiv id is that paper. `null`
 * when the query has no word and no filter is set: every paper would pass.
 */
export function candidateTest(
  rawQuery: string,
  filters: SearchFilters,
): ((paper: Paper) => boolean) | null {
  const arxivId = arxivIdOf(rawQuery);
  if (arxivId !== null) return (paper) => paper.arxiv_id === arxivId;
  const query = parseQuery(rawQuery);
  const terms = [query.text, ...query.phrases].flatMap(termsOf);
  const groups = query.either.map((group) => group.map((alternative) => termsOf(alternative.text)));
  if (terms.length === 0 && groups.length === 0 && activeFilterCount(filters) === 0) {
    return null;
  }
  return (paper) => {
    if (!matchesFilters(paper, filters)) return false;
    if (terms.length === 0 && groups.length === 0) return true;
    const text = foldedText(paper);
    let words: string[] | undefined;
    const paperWords = () => {
      words ??= paperTerms(paper);
      return words;
    };
    const holds = (term: string) => mayHold(term, text, paperWords);
    return (
      terms.every(holds) && groups.every((group) => group.some((either) => either.every(holds)))
    );
  };
}

/** Files a search of every paper reads ahead of the one it tests: their papers wait in memory. */
const READ_AHEAD = 4;

/** How far a search of every stored paper went (UX-51), told after each file it read. */
export interface StoreProgress {
  /** The papers read, as the files hold them: a paper in two files counts twice. */
  read: number;
  /** Those that passed the test, which the index ranks next. */
  found: number;
}

/** How a search of every stored paper keeps what passes its test. */
export interface StoreKeeping {
  /** Papers kept at most, newest first; the others that pass are counted. */
  budget?: number;
  /** What is kept of a paper: Rankings' scan of them all drops their abstracts. */
  keep?: (paper: Paper) => Paper;
}

/** What a search of every stored paper found (PROD-21). */
export interface StoreSearch {
  /** The papers that passed the test, newest file first, within {@link PAPER_BUDGET}. */
  papers: Paper[];
  /** The distinct papers read. */
  searched: number;
  /** Papers that passed the test past the budget, left out. */
  leftOut: number;
  /** What could not be loaded, and was not searched. */
  missing: { days: string[]; years: number[]; recent: boolean };
}

/**
 * Every stored paper of a category through `test` (PROD-21): each day file, the most cited
 * papers of the last 12 months, then each year of the archive, newest first, each file's
 * papers kept only while it is tested, so that memory holds those that pass, not the
 * store (a year of day files would take 480 MB indexed). A paper is read once, from its
 * first file: the day file's record. Past the budget ({@link PAPER_BUDGET} papers kept
 * unless `keeping` says otherwise), the others that pass are only counted; `keeping.keep`
 * says what is kept of each. Files are asked for {@link READ_AHEAD} ahead, the browser
 * keeping them for the next search; one that fails twice is left out and named, unless
 * every one does. `onRead` hears how far it went, at each file.
 */
export async function searchStore(
  category: string,
  holding: StoreHolding,
  test: (paper: Paper) => boolean,
  onRead: (progress: StoreProgress) => void,
  signal?: AbortSignal,
  keeping: StoreKeeping = {},
): Promise<StoreSearch> {
  const { budget = PAPER_BUDGET, keep = (paper: Paper) => paper } = keeping;
  // The most cited of the last 12 months have neither a day nor a year.
  const files: { path: string; day?: string; year?: number }[] = [
    ...holding.days.map(({ date }) => ({ path: `${category}/${date}.json`, day: date })),
    ...(holding.topRecent ? [{ path: `${category}/top-recent.json` }] : []),
    ...[...holding.archiveYears]
      .sort((a, b) => b - a)
      .map((year) => ({ path: `${category}/archive/${year}.json`, year })),
  ];
  const result: StoreSearch = {
    papers: [],
    searched: 0,
    leftOut: 0,
    missing: { days: [], years: [], recent: false },
  };
  const seen = new Set<string>();
  let failure: unknown;
  const progress: StoreProgress = { read: 0, found: 0 };
  const load = (path: string) => readStoreFile(path, signal);
  // Asked for once more when it fails, as a period's day files are; never when the search
  // was left, nor for a file of another schema version, which fail the search.
  const fatal = (error: unknown) => signal?.aborted || error instanceof SchemaVersionError;
  const loadFile = (path: string): Promise<Paper[] | null> => {
    const papers = load(path)
      .catch((error: unknown) => {
        if (fatal(error)) throw error;
        return load(path);
      })
      .catch((error: unknown) => {
        if (fatal(error)) throw error;
        console.warn(`Could not load ${path}`, error);
        failure = error;
        return null;
      });
    // A search left fails the files read ahead too, which nothing awaits any more.
    papers.catch(() => undefined);
    return papers;
  };
  const pending = files.slice(0, READ_AHEAD).map(({ path }) => loadFile(path));
  let rested = performance.now();
  for (const [at, file] of files.entries()) {
    // Files the page kept come without a request, which would have failed.
    if (signal?.aborted) throw new DOMException("The search was left", "AbortError");
    const ahead = files[at + READ_AHEAD];
    if (ahead) pending.push(loadFile(ahead.path));
    const papers = await pending[at];
    // Its papers only wait for the test: the promise would keep them to the end.
    pending[at] = Promise.resolve(null);
    if (!papers) {
      if (file.day !== undefined) result.missing.days.push(file.day);
      else if (file.year !== undefined) result.missing.years.push(file.year);
      else result.missing.recent = true;
      continue;
    }
    for (const paper of papers) {
      if (seen.has(paper.arxiv_id)) continue;
      seen.add(paper.arxiv_id);
      if (!test(paper)) continue;
      if (result.papers.length < budget) result.papers.push(keep(paper));
      else result.leftOut++;
    }
    progress.read += papers.length;
    progress.found = result.papers.length + result.leftOut;
    onRead({ ...progress });
    // Files the page or the browser kept come at once: the page draws the progress between.
    if (performance.now() - rested > 50) {
      await new Promise((resolve) => setTimeout(resolve, 0));
      rested = performance.now();
    }
  }
  const { days, years, recent } = result.missing;
  if (files.length > 0 && days.length + years.length + (recent ? 1 : 0) === files.length) {
    throw failure;
  }
  result.searched = seen.size;
  return result;
}
