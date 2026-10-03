import { between, DEFAULT_PERIOD, isIsoDay, isRange, type Period } from "./period";
import {
  exactly,
  type NameFilter,
  NO_FILTERS,
  type SearchFilters,
  type SortOrder,
  typed,
} from "./search";

export type View = "papers" | "cited" | "graph" | "rankings" | "reading-list" | "about";

const VIEWS: readonly View[] = ["papers", "cited", "graph", "rankings", "reading-list", "about"];
const SORTS: readonly SortOrder[] = ["relevance", "newest", "citations"];

export interface ViewState {
  query: string;
  category: string | null;
  period: Period;
  sort: SortOrder;
  view: View;
  filters: SearchFilters;
  /** arXiv id from a shared `?paper=` link: its card is opened and scrolled into view. */
  paper: string | null;
  /** Year of the archive shown by the highly cited view (`null`: the latest). */
  year: number | null;
}

export const DEFAULT_STATE: ViewState = {
  query: "",
  category: null,
  period: DEFAULT_PERIOD,
  sort: "relevance",
  view: "papers",
  filters: NO_FILTERS,
  paper: null,
  year: null,
};

/** `?from=…&to=…` (a single `from` is one day), else `?range=…`, else the default. */
function readPeriod(params: URLSearchParams): Period {
  const from = params.get("from");
  const to = params.get("to") ?? from;
  if (isIsoDay(from) && isIsoDay(to)) return between(from, to);
  const range = params.get("range");
  return isRange(range) ? { kind: "recent", range } : DEFAULT_PERIOD;
}

/**
 * A name filter from the URL: `exactKey` holds a clicked name (`?by=Hao Li`, `?at=MIT`),
 * `typedKey` typed text (`?author=`, `?aff=`, which links made before exact filters use).
 */
function readName(params: URLSearchParams, exactKey: string, typedKey: string): NameFilter | null {
  const exact = params.get(exactKey);
  if (exact) return exactly(exact);
  const text = params.get(typedKey);
  return text ? typed(text) : null;
}

/** Parse the view state from a query string, so that searches can be shared as links. */
export function readState(search: string): ViewState {
  const params = new URLSearchParams(search);
  return {
    query: params.get("q") ?? "",
    category: params.get("cat"),
    period: readPeriod(params),
    sort: SORTS.find((sort) => sort === params.get("sort")) ?? DEFAULT_STATE.sort,
    view: VIEWS.find((view) => view === params.get("view")) ?? DEFAULT_STATE.view,
    paper: params.get("paper"),
    year: /^\d{4}$/.test(params.get("year") ?? "") ? Number(params.get("year")) : null,
    filters: {
      excludeCrossLists: params.get("xl") === "0",
      author: readName(params, "by", "author"),
      affiliation: readName(params, "at", "aff"),
      subject: params.get("subject"),
      venue: params.get("venue"),
    },
  };
}

/** Serialize the view state, omitting default values to keep links short. */
export function writeState(state: ViewState): string {
  const params = new URLSearchParams();
  const set = (key: string, value: string | null, fallback: string | null = null) => {
    if (value !== null && value !== "" && value !== fallback) params.set(key, value);
  };
  const { period } = state;
  set("q", state.query.trim());
  set("cat", state.category);
  if (period.kind === "dates") {
    set("from", period.from);
    set("to", period.to, period.from);
  } else {
    set("range", period.range, DEFAULT_PERIOD.kind === "recent" ? DEFAULT_PERIOD.range : null);
  }
  set("sort", state.sort, DEFAULT_STATE.sort);
  set("view", state.view, DEFAULT_STATE.view);
  set("paper", state.paper);
  set("year", state.year === null ? null : String(state.year));
  set("xl", state.filters.excludeCrossLists ? "0" : null);
  const { author, affiliation } = state.filters;
  set(author?.exact ? "by" : "author", author?.text ?? null);
  set(affiliation?.exact ? "at" : "aff", affiliation?.text ?? null);
  set("subject", state.filters.subject);
  set("venue", state.filters.venue);
  const query = params.toString();
  return query ? `?${query}` : "";
}

/**
 * The state as far as the Back button is concerned: typing (the query, typed filters) and
 * the sort are left out, so that they replace the current history entry instead of adding
 * one per keystroke.
 */
function navigationKey(state: ViewState): string {
  const { author, affiliation } = state.filters;
  return writeState({
    ...state,
    query: "",
    sort: DEFAULT_STATE.sort,
    filters: {
      ...state.filters,
      author: author?.exact ? author : null,
      affiliation: affiliation?.exact ? affiliation : null,
    },
  });
}

/**
 * Whether going from one state to the other is a step to keep in the browser's history:
 * another view, paper, period, year or category, or a filter set by a click.
 */
export function isNavigation(from: ViewState, to: ViewState): boolean {
  return navigationKey(from) !== navigationKey(to);
}

/**
 * The archive year that holds a paper the stored days do not: one announced before the
 * oldest day, in a year the archive has. `null` for a paper of the days.
 */
export function archiveYearOf(
  announced: string,
  oldestDay: string | undefined,
  archiveYears: readonly number[],
): number | null {
  const year = Number(announced.slice(0, 4));
  return oldestDay !== undefined && announced < oldestDay && archiveYears.includes(year)
    ? year
    : null;
}

/**
 * A link to one paper, for its Share control: its archive year in the Highly cited view
 * when it is archived (an older paper has no day file), else its announcement day.
 */
export function paperLink(
  paper: { arxiv_id: string; announced: string },
  where: {
    category: string | null;
    oldestDay: string | undefined;
    archiveYears: readonly number[];
  },
): string {
  const year = archiveYearOf(paper.announced, where.oldestDay, where.archiveYears);
  return writeState({
    ...DEFAULT_STATE,
    category: where.category,
    ...(year === null
      ? { period: between(paper.announced, paper.announced) }
      : { view: "cited" as const, year }),
    paper: paper.arxiv_id,
  });
}
