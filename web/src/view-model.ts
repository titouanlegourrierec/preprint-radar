/**
 * What a view of the list shows, worked out once from the URL state (DEBT-2): which papers
 * it loads, how it orders them, and which controls its header offers. `app.tsx` and its
 * components read this instead of testing the view here and there.
 */
import type { ViewState } from "./url-state";

/** An order the list offers, as its sort control shows it. */
export type SortChoice = "relevance" | "newest" | "citations" | "rising" | "stars" | "custom";

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
  /** The most starred code first (PROD-18): the sort asks it and stars are known. */
  starred: boolean;
  /** Announcement order: Newest, or relevance without search words. */
  newest: boolean;
  /**
   * The reading list's own order (UX-39), which drag and drop and Alt+arrows arrange: its
   * default without search words, as relevance is the others'.
   */
  custom: boolean;
  /** Day headings fold the list: announcement order, outside the highly cited view. */
  groupByDay: boolean;
  /**
   * Each card says its rank in the order shown (UX-36): the highly cited view, always
   * ranked, by citations, gains or stars.
   */
  ranked: boolean;
  /** The orders the sort control offers, in order; empty when it does not show. */
  sorts: SortChoice[];
  /** The order pressed among them. */
  sorted: SortChoice;
  /** The "How is relevance computed?" help next to the sort control. */
  relevanceHelp: boolean;
  /** The "Hide seen" toggle: the Papers view only, where papers are triaged. */
  hideSeen: boolean;
  /** The "Show abstracts" toggle: Papers and Highly cited (the reading list always shows them). */
  abstracts: boolean;
  /** The Export menu, for the results shown: Papers, Highly cited and the reading list. */
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
 * phrases or exclusions), `gainsKnown` once two weekly refreshes of the counts exist,
 * `starsKnown` once papers loaded have the stars of their code (`code.json`).
 */
export function viewModel(
  state: Pick<ViewState, "view" | "sort" | "year">,
  {
    hasSearchWords,
    gainsKnown,
    starsKnown = false,
  }: { hasSearchWords: boolean; gainsKnown: boolean; starsKnown?: boolean },
): ViewModel {
  const { view, sort } = state;
  const cited = view === "cited";
  const rankings = view === "rankings";
  const listed = view === "papers" || view === "reading-list";
  const starred = sort === "stars" && starsKnown && (listed || cited);
  const byCount = !starred && (cited || sort === "citations" || sort === "rising");
  const rising = sort === "rising" && gainsKnown;
  // Most starred before the stars are known is the view's own order, as relevance is; so
  // is the reading list's own order elsewhere.
  const ownOrder = sort === "relevance" || sort === "custom" || (sort === "stars" && !starred);
  const readingList = view === "reading-list";
  const custom = readingList && (sort === "custom" || (ownOrder && !hasSearchWords));
  const relevance = ownOrder && !custom;
  const newest = sort === "newest" || (relevance && !hasSearchWords);
  const sorts: SortChoice[] =
    listed || (cited && (gainsKnown || starsKnown))
      ? [
          ...(readingList ? (["custom"] as const) : []),
          ...(hasSearchWords && !cited ? (["relevance"] as const) : []),
          ...(cited ? [] : (["newest"] as const)),
          "citations",
          ...(gainsKnown ? (["rising"] as const) : []),
          ...(starsKnown ? (["stars"] as const) : []),
        ]
      : [];
  return {
    cited,
    rankings,
    archived: showsArchive(state),
    triaged: view === "papers",
    byCount,
    rising,
    starred,
    newest,
    custom,
    groupByDay: !byCount && !starred && !custom && (!hasSearchWords || sort === "newest"),
    ranked: cited,
    sorts,
    sorted: sortedBy({ byCount, rising, starred, newest, custom }),
    relevanceHelp: sorts.includes("relevance"),
    hideSeen: view === "papers",
    abstracts: view === "papers" || cited,
    exports: listed || cited,
  };
}

/** The order pressed: without counts nor Newest, relevance with search words. */
function sortedBy({
  byCount,
  rising,
  starred,
  newest,
  custom,
}: {
  byCount: boolean;
  rising: boolean;
  starred: boolean;
  newest: boolean;
  custom: boolean;
}): SortChoice {
  if (custom) return "custom";
  if (starred) return "stars";
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
