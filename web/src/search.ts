import MiniSearch, { type SearchResult as MiniSearchResult, type Options } from "minisearch";
import { codeUrl } from "./code";
import { subjectCode } from "./format";
import { wholeWord, wordStarts } from "./highlight";
import { acronymOf, institutionsOf, namedInstitutions } from "./institutions";
import { fold, searchKey } from "./text";
import type { Paper } from "./types";
import { ANY_VENUE, matchesVenue } from "./venues";

export { ANY_VENUE };

/**
 * Order of results. The index has no citation counts nor stars: `citations`, `rising` and
 * `stars` order them like `relevance` (best match first with search words, else newest
 * first), and the caller ranks them with {@link byCitations}, {@link byGains} or
 * {@link byStars}, which keep that order among equal counts (CIT-6).
 */
/** `custom`: the reading list's own order (UX-39), which the index leaves to its caller. */
export type SortOrder = "relevance" | "newest" | "citations" | "rising" | "stars" | "custom";

/**
 * An author or affiliation filter: a name clicked on a card, a Rankings row or a graph
 * node (`exact`: that name only), or text typed in the sidebar (word prefixes).
 */
export interface NameFilter {
  text: string;
  exact: boolean;
}

export interface SearchFilters {
  excludeCrossLists: boolean;
  /** Papers that link their code (`codeUrl`). */
  withCode: boolean;
  author: NameFilter | null;
  affiliation: NameFilter | null;
  subject: string | null;
  /**
   * A venue as detected in the comments (e.g. "ECCV 2026"), a family of them ("ECCV*",
   * `venues.ts`), or {@link ANY_VENUE}.
   */
  venue: string | null;
}

/** A filter on text typed by the user. */
export function typed(text: string): NameFilter {
  return { text, exact: false };
}

/** A filter on one name, as clicked. */
export function exactly(text: string): NameFilter {
  return { text, exact: true };
}

export const NO_FILTERS: SearchFilters = {
  excludeCrossLists: false,
  withCode: false,
  author: null,
  affiliation: null,
  subject: null,
  venue: null,
};

export interface ParsedQuery {
  /** Free text, matched with prefix and fuzzy search. */
  text: string;
  /**
   * `"quoted phrases"` that must appear as whole words, in any searched field, ignoring
   * case, accents and punctuation ("self supervised" matches "self-supervised").
   */
  phrases: string[];
  /** `-words`: no word of any searched field may start with them. */
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
const MIN_PREFIX_LENGTH = 4;
const tokenize: (text: string) => string[] = MiniSearch.getDefault("tokenize");

/** Whether a query term matches the words it starts: the last one typed, from 4 letters. */
function isPrefix(term: string, index: number, terms: readonly string[]): boolean {
  return index === terms.length - 1 && term.length >= MIN_PREFIX_LENGTH;
}
const MIN_FUZZY_LENGTH = 7;

/**
 * How much more a paper scores for holding a query's words side by side (SRCH-18): three
 * times as much with all of them, so that "text-to-image generation" in an abstract ranks
 * before the three words apart, but not before them in a title, which weighs three times
 * an abstract. Over the 30 days of 2026-10-15, the top 20 results of 17 queries of two or
 * more words held them as typed 84% of the time, 95% with it ("3d reconstruction": 10 of
 * 20, then 20).
 */
const ADJACENCY_BOOST = 2;

/** What lies between two words, as {@link searchKey} sees them: anything but letters and digits. */
const NOT_A_WORD = "[^\\p{L}\\p{N}]+";

/**
 * What a query's words must hold side by side to rank first (SRCH-18): each two of its
 * words that follow each other, with the stop words between them, as patterns over a
 * paper's {@link fold}ed text ("text to image" and "image generation" for "text-to-image
 * generation"). Whole words with anything but letters and digits between them, as
 * {@link searchKey} sees them, the last one a prefix as the search takes it: a pattern
 * costs a fraction of the key of every paper a broad search finds.
 */
function adjacentPatterns(text: string): RegExp[] {
  const words = searchKey(text).split(" ");
  const kept = words.flatMap((word, at) => (processTerm(word) ? [at] : []));
  return kept.slice(1).map((end, at) => {
    const piece = words.slice(kept[at], end + 1).join(NOT_A_WORD);
    const prefix = at === kept.length - 2 && (words[end]?.length ?? 0) >= MIN_PREFIX_LENGTH;
    return new RegExp(`(?<![\\p{L}\\p{N}])${piece}${prefix ? "" : "(?![\\p{L}\\p{N}])"}`, "u");
  });
}
export function parseQuery(raw: string): ParsedQuery {
  const phrases: string[] = [];
  const excluded: string[] = [];
  const text = raw
    .replace(/"([^"]+)"/g, (_, phrase: string) => {
      const key = searchKey(phrase);
      if (key) phrases.push(key);
      return " ";
    })
    .replace(/(^|\s)-(\S+)/g, (_, space: string, word: string) => {
      const key = searchKey(word);
      if (key) excluded.push(key);
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
      return [...new Set([...(paper.affiliations ?? []), ...namedInstitutions(paper)])].join(" ");
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

/**
 * Every searched field of the paper, as one {@link searchKey} with a space at both ends,
 * so that phrases and exclusions match whole words: `" gan "` is not in `" organ "`.
 */
function constraintText(paper: Paper): string {
  return ` ${searchKey(SEARCHED_FIELDS.map((field) => fieldValue(paper, field)).join(" "))} `;
}

function newestFirst(a: SearchResult, b: SearchResult): number {
  return (
    b.paper.announced.localeCompare(a.paper.announced) ||
    b.paper.arxiv_id.localeCompare(a.paper.arxiv_id)
  );
}

const INDEX_OPTIONS: Options<Paper> = {
  idField: "arxiv_id",
  fields: SEARCHED_FIELDS,
  extractField: (paper: Paper, field: string) =>
    field === "arxiv_id" ? paper.arxiv_id : fieldValue(paper, field),
  processTerm,
  searchOptions: {
    boost: FIELD_BOOSTS,
    combineWith: "AND",
    // Type-ahead on the word being typed only, and never on a short acronym: "gan" is
    // not "Gandhi", "mit" not "mitigate". One typo from 7 letters: "detection" is not
    // "selection". Exact matches weigh most.
    prefix: isPrefix,
    fuzzy: (term: string) => (term.length >= MIN_FUZZY_LENGTH ? 1 : false),
    weights: { fuzzy: 0.2, prefix: 0.5 },
  },
};

/** Papers added to the full-text index between two yields to the browser. */
const WARM_CHUNK = 200;

function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/**
 * Full-text index over a set of papers, with structured filters.
 *
 * The full-text index is built only when needed (60 ms for a day of cs.CV, about a second
 * for 20): a list without search words never uses it, so it shows at once. {@link warm}
 * builds it in chunks while the page stays responsive, and a search before it ends adds
 * the papers left at once.
 */
export class PaperIndex {
  private readonly papers: Map<string, Paper>;
  /** The papers in the order they enter the full-text index, the first `indexed` in it. */
  private readonly queue: Paper[];
  private indexed = 0;
  private fullText: MiniSearch<Paper> | null = null;
  /** {@link constraintText} of each paper, built when a query first needs it. */
  private readonly constraints = new Map<string, string>();
  /** The folded text of each paper, built when a query of several words first needs it. */
  private readonly folded = new Map<string, string>();

  constructor(papers: Paper[]) {
    // A paper cross-listed in several loaded days would otherwise be indexed twice.
    this.papers = new Map(papers.map((paper) => [paper.arxiv_id, paper]));
    this.queue = [...this.papers.values()];
  }

  /** Whether every paper is in the full-text index, so that a search indexes nothing. */
  get ready(): boolean {
    return this.indexed === this.queue.length;
  }

  /**
   * Build the full-text index, a chunk of papers at a time, yielding to the browser in
   * between; it stops early when `signal` aborts (the papers are no longer shown).
   */
  async warm(signal?: AbortSignal): Promise<void> {
    while (!(this.ready || signal?.aborted)) {
      const end = Math.min(this.indexed + WARM_CHUNK, this.queue.length);
      this.index().addAll(this.queue.slice(this.indexed, end));
      this.indexed = end;
      await yieldToBrowser();
    }
  }

  /** The full-text index with every paper: those {@link warm} has not reached yet are added now. */
  private complete(): MiniSearch<Paper> {
    const index = this.index();
    if (!this.ready) {
      index.addAll(this.queue.slice(this.indexed));
      this.indexed = this.queue.length;
    }
    return index;
  }

  private index(): MiniSearch<Paper> {
    this.fullText ??= new MiniSearch<Paper>(INDEX_OPTIONS);
    return this.fullText;
  }

  get size(): number {
    return this.papers.size;
  }

  /** Whether the paper is indexed. */
  has(arxivId: string): boolean {
    return this.papers.has(arxivId);
  }

  /** The indexed paper with this identifier. */
  get(arxivId: string): Paper | undefined {
    return this.papers.get(arxivId);
  }

  /** Every indexed paper, in no particular order. */
  all(): Paper[] {
    return [...this.papers.values()];
  }

  search(rawQuery: string, filters: SearchFilters, sort: SortOrder): SearchResult[] {
    const query = parseQuery(rawQuery);
    // The words typed are highlighted as the search matched them, whole or, for the last
    // one, as a prefix: not what a typo allowance matched ("depth" does not mark "death"),
    // nor longer words for an acronym ("vit" does not mark "vitamins").
    const typedTerms = tokenize(query.text)
      .map(processTerm)
      .filter((term): term is string => Boolean(term))
      .map((term, index, terms) => (isPrefix(term, index, terms) ? term : wholeWord(term)));
    // A pasted arXiv identifier or link means that paper, whatever the filters.
    const arxivId = arxivIdOf(rawQuery);
    if (arxivId !== null) {
      const paper = this.papers.get(arxivId);
      return paper ? [{ paper, score: 0, highlights: [] }] : [];
    }
    // Stop words alone ("the", "on" while typing "on-device") search nothing: every paper.
    const results = typedTerms.length
      ? this.complete()
          .search(query.text)
          .flatMap((hit) => this.toResult(hit, typedTerms))
      : [...this.papers.values()].map((paper) => ({ paper, score: 0, highlights: [] }));

    const filtered = results.filter(
      ({ paper }) => matchesFilters(paper, filters) && this.matchesConstraints(paper, query),
    );
    // The names filtered on are highlighted apart, in the author and affiliation lines only
    // (`nameHighlights`): "Li" would mark "lightweight" in a title.
    for (const result of filtered) {
      result.highlights.push(...query.phrases);
    }
    // Only Newest ignores the match: Most cited and Rising keep it among equal counts.
    if (sort === "newest" || typedTerms.length === 0) return filtered.sort(newestFirst);
    const pieces = adjacentPatterns(query.text);
    if (pieces.length > 0) {
      for (const result of filtered) {
        const text = this.foldedOf(result.paper);
        const together = pieces.filter((piece) => piece.test(text)).length;
        result.score *= 1 + (ADJACENCY_BOOST * together) / pieces.length;
      }
    }
    return filtered.sort((a, b) => b.score - a.score || newestFirst(a, b));
  }

  /** Every searched field of a paper, {@link fold}ed, built once: what side by side is read in. */
  private foldedOf(paper: Paper): string {
    let text = this.folded.get(paper.arxiv_id);
    if (text === undefined) {
      text = fold(SEARCHED_FIELDS.map((field) => fieldValue(paper, field)).join(" "));
      this.folded.set(paper.arxiv_id, text);
    }
    return text;
  }

  /** {@link constraintText} of a paper, built once. */
  private constraintsOf(paper: Paper): string {
    let text = this.constraints.get(paper.arxiv_id);
    if (text === undefined) {
      text = constraintText(paper);
      this.constraints.set(paper.arxiv_id, text);
    }
    return text;
  }

  private matchesConstraints(paper: Paper, query: ParsedQuery): boolean {
    if (query.phrases.length === 0 && query.excluded.length === 0) return true;
    const text = this.constraintsOf(paper);
    return (
      query.phrases.every((phrase) => text.includes(` ${phrase} `)) &&
      // A prefix, as free text matches: "-survey" leaves out "surveys" too.
      !query.excluded.some((word) => text.includes(` ${word}`))
    );
  }

  private toResult(hit: MiniSearchResult, typedTerms: readonly string[]): SearchResult[] {
    const paper = this.papers.get(String(hit.id));
    return paper ? [{ paper, score: hit.score, highlights: [...typedTerms] }] : [];
  }
}

// "2609.38156", "arXiv:2609.38156v2", "https://arxiv.org/abs/2609.38156", "cs/0601001".
const ARXIV_ID_RE =
  /^(?:arxiv:\s*|(?:https?:\/\/)?(?:www\.)?arxiv\.org\/(?:abs|pdf|html)\/)?(\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?\/\d{7})(?:v\d+)?(?:\.pdf)?\/?$/i;

/** The arXiv identifier a query consists of, without its version; `null` for any other query. */
export function arxivIdOf(query: string): string | null {
  return ARXIV_ID_RE.exec(query.trim())?.[1] ?? null;
}

/** How many filters narrow the papers, for the Filters summary. */
export function activeFilterCount(filters: SearchFilters): number {
  return [
    isActive(filters.author),
    isActive(filters.affiliation),
    filters.venue !== null,
    filters.subject !== null,
    filters.excludeCrossLists,
    filters.withCode,
  ].filter(Boolean).length;
}

/** Whether the filter filters anything: an empty one does not. */
export function isActive(filter: NameFilter | null): filter is NameFilter {
  return filter !== null && searchKey(filter.text) !== "";
}

/**
 * Whether consecutive words of `value` start with the words of `text`, in order, ignoring
 * case, accents and punctuation: "kaist" matches "KAIST, Daejeon", "perez" matches
 * "Lozano-Pérez" and "hao li" matches "Hao Lin", but "hao li" does not match "Chuanhao Li".
 */
export function startsWords(value: string, text: string): boolean {
  return hasWords(value, text, (valueWord, word) => valueWord.startsWith(word));
}

/** Whether consecutive words of `value` are the words of `text`, whole. */
function hasWholeWords(value: string, text: string): boolean {
  return hasWords(value, text, (valueWord, word) => valueWord === word);
}

function hasWords(
  value: string,
  text: string,
  same: (valueWord: string, word: string) => boolean,
): boolean {
  const words = searchKey(text).split(" ");
  const valueWords = searchKey(value).split(" ");
  for (let start = 0; start + words.length <= valueWords.length; start++) {
    if (words.every((word, offset) => same(valueWords[start + offset] ?? "", word))) return true;
  }
  return false;
}

function matchesAuthor(paper: Paper, filter: NameFilter): boolean {
  if (!filter.exact) return paper.authors.some((author) => startsWords(author, filter.text));
  const key = searchKey(filter.text);
  return paper.authors.some((author) => searchKey(author) === key);
}

function matchesAffiliation(paper: Paper, filter: NameFilter): boolean {
  if (filter.exact) {
    // The institutions as the graph and Rankings count them, whatever the strings say.
    const key = searchKey(filter.text);
    return namedInstitutions(paper).some((name) => searchKey(name) === key);
  }
  const values = [...(paper.affiliations ?? []), ...namedInstitutions(paper)];
  // A known acronym typed whole means its institution, however it is written ("NUS" finds
  // "National University of Singapore"), and is a whole word: "HKU" is not "HKUST".
  const acronym = acronymOf(filter.text);
  if (acronym !== null) {
    return (
      matchesAffiliation(paper, exactly(acronym)) ||
      values.some((value) => hasWholeWords(value, filter.text))
    );
  }
  return values.some((value) => startsWords(value, filter.text));
}

/**
 * The subjects a paper is listed under, primary or cross-listed (SRCH-9): its `subjects`,
 * which the store starts with the primary one, and that one for a paper kept in a browser
 * before `subjects` was (`reading-list.ts` gives it none).
 */
export function subjectsOf(paper: Paper): string[] {
  const primary = paper.primary_subject;
  return primary && !paper.subjects.includes(primary)
    ? [primary, ...paper.subjects]
    : paper.subjects;
}

/**
 * Whether a paper is listed under a subject, compared by code: the archive writes some
 * subjects as a bare code ("math.ST") where the day files give the name, and a link may
 * hold either (SRCH-9).
 */
function listedUnder(paper: Paper, subject: string): boolean {
  const code = subjectCode(subject);
  return subjectsOf(paper).some((listed) => subjectCode(listed) === code);
}

/**
 * A clicked author or institution matches that name only (folded and with punctuation
 * collapsed, as {@link searchKey} does), and an institution by the name the graph gives it,
 * whatever the affiliation string ("CMU" for "Carnegie Mellon University"). Typed text
 * matches word prefixes of authors, or of affiliations and their institutions'
 * names: see {@link startsWords}.
 */
export function matchesFilters(paper: Paper, filters: SearchFilters): boolean {
  return (
    !(filters.excludeCrossLists && paper.cross_list_from !== null) &&
    (!filters.withCode || codeUrl(paper) !== null) &&
    (!isActive(filters.author) || matchesAuthor(paper, filters.author)) &&
    // Institutions are only named when an affiliation filter needs them.
    (!isActive(filters.affiliation) || matchesAffiliation(paper, filters.affiliation)) &&
    (filters.subject === null || listedUnder(paper, filters.subject)) &&
    (filters.venue === null || matchesVenue(paper.venue, filters.venue))
  );
}

/** What the author and affiliation filters mark on a card (SRCH-8). */
export interface NameHighlights {
  /** In the author line only. */
  authors: string[];
  /** In the affiliation line only. */
  affiliations: string[];
  /**
   * The key of the institution clicked: a card marks whole the affiliations it names,
   * however they write it ("IIT Kanpur" for Indian Institute of Technology Kanpur).
   */
  institution: string | null;
}

/** A filter's needles: a clicked name whole, typed words as word starts, as each matches. */
function filterNeedles(filter: NameFilter | null): string[] {
  if (!isActive(filter)) return [];
  // The filters compare `searchKey`s, whose punctuation the needle's words may stand
  // across: "Julia A. Schnabel" marks "Julia A Schnabel", "Xi'an" marks "Xi’an".
  if (filter.exact) return [wholeWord(searchKey(filter.text))];
  // Each typed word is one needle, its own punctuation included ("AT&T" is "at t"), whose
  // pieces start words as the filter's do: "J.Smith" marks "John Smith". One letter alone
  // stays a plain needle, which marks nothing.
  return filter.text
    .split(/\s+/)
    .map(searchKey)
    .filter((word) => word && !STOP_WORDS.has(word))
    .map((word) => (word.includes(" ") ? wordStarts(word) : word));
}

/**
 * What the author and affiliation filters highlight, each in its own line of a card
 * (SRCH-8): a clicked name as a whole ("Hao Li", not every word starting with "li"), typed
 * text as word starts (each piece of a typed word too), and the affiliations of a clicked
 * institution.
 */
export function nameHighlights(filters: SearchFilters): NameHighlights {
  const { affiliation } = filters;
  return {
    authors: filterNeedles(filters.author),
    affiliations: filterNeedles(affiliation),
    institution: affiliation?.exact && isActive(affiliation) ? searchKey(affiliation.text) : null,
  };
}

/**
 * What to mark in one of a paper's affiliations: the search words, the affiliation
 * filter's needles, and the whole affiliation when it names the institution clicked.
 */
export function affiliationNeedles(
  paper: Paper,
  affiliation: string,
  names: NameHighlights,
  highlights: readonly string[],
): string[] {
  const institution = institutionsOf(paper)[paper.affiliations?.indexOf(affiliation) ?? -1];
  const clicked =
    names.institution !== null && institution && searchKey(institution) === names.institution;
  return [
    ...highlights,
    ...names.affiliations,
    ...(clicked ? [wholeWord(searchKey(affiliation))] : []),
  ];
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

/**
 * The subject filter's choices (SRCH-9): the subjects the papers are listed under, primary
 * or cross-listed, the `limit` most frequent first. Counted over every paper loaded, not
 * the results, so that choosing one leaves the others to choose from; the one chosen stays
 * listed past the limit, or with a count of 0 when no paper has it (a shared link's).
 */
export function subjectFacets(
  papers: Iterable<Paper>,
  chosen: string | null,
  limit: number,
): FacetCount[] {
  // One choice per code, named in full where some paper names it (SRCH-9).
  const byCode = new Map<string, FacetCount>();
  for (const { value, count } of valueCounts(papers, subjectsOf, Number.POSITIVE_INFINITY)) {
    const code = subjectCode(value);
    const known = byCode.get(code);
    const named = known === undefined || (value !== code && known.value === code);
    byCode.set(code, { value: named ? value : known.value, count: (known?.count ?? 0) + count });
  }
  const subjects = [...byCode.values()].sort(
    (a, b) => b.count - a.count || a.value.localeCompare(b.value),
  );
  if (chosen === null) return subjects.slice(0, limit);
  // The choice keeps the value the URL holds, so that the select shows it chosen.
  const code = subjectCode(chosen);
  const index = subjects.findIndex(({ value }) => subjectCode(value) === code);
  const chosenFacet = { value: chosen, count: subjects[index]?.count ?? 0 };
  const listed = subjects.slice(0, limit).map((facet, at) => (at === index ? chosenFacet : facet));
  return index >= 0 && index < limit ? listed : [...listed, chosenFacet];
}

/**
 * Results ranked by citation count, most cited first, papers without a known count after
 * those with none; stable for equal counts, which keep their relevance or newest order.
 */
export function byCitations(
  results: readonly SearchResult[],
  counts: ReadonlyMap<string, number>,
): SearchResult[] {
  const count = (result: SearchResult) => counts.get(result.paper.arxiv_id) ?? -1;
  return [...results].sort((a, b) => count(b) - count(a));
}

/**
 * The results by citations gained between the last two weekly refreshes (CIT-9), the most
 * first, then by citations: papers that gained none keep the order of the most cited.
 */
export function byGains(
  results: readonly SearchResult[],
  gains: ReadonlyMap<string, number>,
  counts: ReadonlyMap<string, number>,
): SearchResult[] {
  const gain = (result: SearchResult) => gains.get(result.paper.arxiv_id) ?? 0;
  return byCitations(results, counts).sort((a, b) => gain(b) - gain(a));
}

/**
 * Results by the GitHub stars of the code they link (PROD-18), the most first; papers
 * whose stars are not theirs alone (a repository other papers link too, or a folder of
 * one) rank with those without stars, after them. Stable, as {@link byCitations}.
 */
export function byStars(results: readonly SearchResult[]): SearchResult[] {
  const stars = ({ paper: { code } }: SearchResult) =>
    code?.stars !== undefined && !code.shared ? code.stars : -1;
  return [...results].sort((a, b) => stars(b) - stars(a));
}

/**
 * Whether most results share one citation count (90%), so that ranking by citations says
 * little: recent days, where nearly every count is 0.
 */
export function mostlyTied(
  results: readonly SearchResult[],
  counts: ReadonlyMap<string, number>,
): boolean {
  if (results.length < 10) return false;
  const tally = new Map<number, number>();
  for (const { paper } of results) {
    const count = counts.get(paper.arxiv_id) ?? -1;
    tally.set(count, (tally.get(count) ?? 0) + 1);
  }
  return Math.max(...tally.values()) / results.length > 0.9;
}
