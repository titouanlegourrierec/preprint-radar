/**
 * What a view of the list shows, worked out once from the URL state (DEBT-2): which papers
 * it loads, how it orders them, and which controls its header offers. `app.tsx` and its
 * components read this instead of testing the view here and there.
 */
import type { ViewState } from "./url-state";

/** An order the list offers, as its sort control shows it. */
export type SortChoice = "relevance" | "newest" | "citations" | "rising";

export interface ViewModel {
  /** The Highly cited view: archive years, ranked by citations. */
  cited: boolean;
  rankings: boolean;
  /** The papers loaded are archive years, not recent days. */
  archived: boolean;
  /** Papers can be marked seen and hidden: the Papers view only. */
  triaged: boolean;
  /** The list is ranked by citations, or by citations gained (Rising). */
  byCount: boolean;
  /** Rising papers first: the sort asks it and gains are known. */
  rising: boolean;
  /** Announcement order: Newest, or relevance without search words. */
  newest: boolean;
  /** Day headings fold the list: announcement order, outside the highly cited view. */
  groupByDay: boolean;
  /** The orders the sort control offers, in order; empty when it does not show. */
  sorts: SortChoice[];
  /** The order pressed among them. */
  sorted: SortChoice;
  /** The "How is relevance computed?" help next to the sort control. */
  relevanceHelp: boolean;
  /** Hide seen and Show abstracts. */
  toggles: boolean;
  /** The Export menu, for the results shown. */
  exports: boolean;
}

/** Whether a state shows archive years: Highly cited always, the graph and Rankings given some. */
export function showsArchive(state: Pick<ViewState, "view" | "year">): boolean {
  return (
    state.view === "cited" ||
    ((state.view === "graph" || state.view === "rankings") && state.year !== null)
  );
}

/**
 * The view model of a state: `hasSearchWords` when the query holds words (not only
 * phrases or exclusions), `gainsKnown` once two weekly refreshes of the counts exist.
 */
export function viewModel(
  state: Pick<ViewState, "view" | "sort" | "year">,
  { hasSearchWords, gainsKnown }: { hasSearchWords: boolean; gainsKnown: boolean },
): ViewModel {
  const { view, sort } = state;
  const cited = view === "cited";
  const rankings = view === "rankings";
  const listed = view === "papers" || view === "reading-list";
  const byCount = cited || sort === "citations" || sort === "rising";
  const rising = sort === "rising" && gainsKnown;
  const newest = sort === "newest" || (sort === "relevance" && !hasSearchWords);
  const sorts: SortChoice[] =
    listed || (cited && gainsKnown)
      ? [
          ...(hasSearchWords && !cited ? (["relevance"] as const) : []),
          ...(cited ? [] : (["newest"] as const)),
          "citations",
          ...(gainsKnown ? (["rising"] as const) : []),
        ]
      : [];
  return {
    cited,
    rankings,
    archived: showsArchive(state),
    triaged: view === "papers",
    byCount,
    rising,
    newest,
    groupByDay: !byCount && (!hasSearchWords || sort === "newest"),
    sorts,
    sorted: sortedBy({ byCount, rising, newest }),
    relevanceHelp: sorts.includes("relevance"),
    toggles: view === "papers",
    exports: view === "papers" || cited,
  };
}

/** The order pressed: without counts nor Newest, relevance with search words. */
function sortedBy({
  byCount,
  rising,
  newest,
}: {
  byCount: boolean;
  rising: boolean;
  newest: boolean;
}): SortChoice {
  if (rising) return "rising";
  if (byCount) return "citations";
  return newest ? "newest" : "relevance";
}

/** What the results header counts: the papers shown, of how many, and which. */
export interface CountLine {
  shown: number;
  total: number;
  /** "saved paper", "highly cited cs.CV paper", "cs.CV paper". */
  noun: string;
  /** After the count: "first published in 2024", "· 3 seen papers hidden". */
  tail?: string;
}
