import { between, DEFAULT_PERIOD, isIsoDay, isRange, type Period } from "./period";
import { NO_FILTERS, type SearchFilters, type SortOrder } from "./search";

export type View = "papers" | "cited" | "graph" | "rankings" | "reading-list";

const VIEWS: readonly View[] = ["papers", "cited", "graph", "rankings", "reading-list"];
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
      author: params.get("author"),
      affiliation: params.get("aff"),
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
  set("author", state.filters.author);
  set("aff", state.filters.affiliation);
  set("subject", state.filters.subject);
  set("venue", state.filters.venue);
  const query = params.toString();
  return query ? `?${query}` : "";
}
