import { NO_FILTERS, type SearchFilters, type SortOrder } from "./search";

export const RANGES = {
  "1": { label: "Latest day", days: 1 },
  "5": { label: "Last 5 days", days: 5 },
  "20": { label: "Last 20 days", days: 20 },
  all: { label: "All days", days: Number.POSITIVE_INFINITY },
} as const;

export type RangeKey = keyof typeof RANGES;
export type View = "papers" | "reading-list";

export interface ViewState {
  query: string;
  category: string | null;
  range: RangeKey;
  sort: SortOrder;
  view: View;
  filters: SearchFilters;
}

export const DEFAULT_STATE: ViewState = {
  query: "",
  category: null,
  range: "5",
  sort: "relevance",
  view: "papers",
  filters: NO_FILTERS,
};

function isRange(value: string | null): value is RangeKey {
  return value !== null && Object.hasOwn(RANGES, value);
}

/** Parse the view state from a query string, so that searches can be shared as links. */
export function readState(search: string): ViewState {
  const params = new URLSearchParams(search);
  const range = params.get("range");
  return {
    query: params.get("q") ?? "",
    category: params.get("cat"),
    range: isRange(range) ? range : DEFAULT_STATE.range,
    sort: params.get("sort") === "newest" ? "newest" : "relevance",
    view: params.get("view") === "reading-list" ? "reading-list" : "papers",
    filters: {
      excludeCrossLists: params.get("xl") === "0",
      author: params.get("author"),
      affiliation: params.get("aff"),
      subject: params.get("subject"),
    },
  };
}

/** Serialize the view state, omitting default values to keep links short. */
export function writeState(state: ViewState): string {
  const params = new URLSearchParams();
  const set = (key: string, value: string | null, fallback: string | null = null) => {
    if (value !== null && value !== "" && value !== fallback) params.set(key, value);
  };
  set("q", state.query.trim());
  set("cat", state.category);
  set("range", state.range, DEFAULT_STATE.range);
  set("sort", state.sort, DEFAULT_STATE.sort);
  set("view", state.view, DEFAULT_STATE.view);
  set("xl", state.filters.excludeCrossLists ? "0" : null);
  set("author", state.filters.author);
  set("aff", state.filters.affiliation);
  set("subject", state.filters.subject);
  const query = params.toString();
  return query ? `?${query}` : "";
}
