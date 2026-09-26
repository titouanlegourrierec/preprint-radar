import { useEffect, useMemo, useState } from "preact/hooks";
import { toBibtexFile } from "./bibtex";
import { GraphView } from "./components/GraphView";
import { PaperList } from "./components/PaperList";
import { Sidebar } from "./components/Sidebar";
import { loadDays, loadIndex } from "./data";
import { formatDay } from "./format";
import { selectDays } from "./period";
import { loadShowAbstracts, saveShowAbstracts } from "./preferences";
import { loadReadingList, saveReadingList } from "./reading-list";
import {
  facetCounts,
  NO_FILTERS,
  PaperIndex,
  parseQuery,
  type SearchFilters,
  type SearchResult,
  valueCounts,
} from "./search";
import type { Paper, StoreIndex } from "./types";
import { readState, type ViewState, writeState } from "./url-state";

const SEARCH_DEBOUNCE_MS = 150;
const FACET_SIZE = 12;
const SUGGESTION_SIZE = 300;
const RELEVANCE_HELP =
  "Relevance ranks papers by how well they match your search words. Rarer words weigh more, " +
  "and a match counts most in the title, then in authors, affiliations, the abstract and " +
  "comments. Exact words count more than partial or approximate ones.";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: PaperIndex };

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function download(filename: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  URL.revokeObjectURL(url);
}

export function App() {
  const [state, setState] = useState<ViewState>(() => readState(window.location.search));
  const [storeIndex, setStoreIndex] = useState<StoreIndex | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [readingList, setReadingList] = useState<Paper[]>(loadReadingList);
  const [showAbstracts, setShowAbstracts] = useState(loadShowAbstracts);
  const [showRelevanceHelp, setShowRelevanceHelp] = useState(false);
  const query = useDebounced(state.query, SEARCH_DEBOUNCE_MS);

  const update = (patch: Partial<ViewState>) => setState((current) => ({ ...current, ...patch }));
  const setFilters = (filters: SearchFilters) => update({ filters });

  // Keep the URL in sync so that any search can be shared or bookmarked.
  useEffect(() => {
    const url = `${window.location.pathname}${writeState({ ...state, query })}`;
    window.history.replaceState(null, "", url);
  }, [state, query]);

  useEffect(() => {
    loadIndex()
      .then(setStoreIndex)
      .catch((error: unknown) => setLoad({ status: "error", message: String(error) }));
  }, []);

  const categories = storeIndex ? Object.keys(storeIndex.categories).sort() : [];
  const category =
    state.category && categories.includes(state.category) ? state.category : categories[0];
  const storeDays = (category && storeIndex?.categories[category]) || [];

  useEffect(() => {
    if (!storeIndex || !category) return;
    const days = selectDays(storeIndex.categories[category] ?? [], state.period);
    let cancelled = false;
    setLoad({ status: "loading" });
    loadDays(category, days)
      .then((papers) => !cancelled && setLoad({ status: "ready", index: new PaperIndex(papers) }))
      .catch(
        (error: unknown) => !cancelled && setLoad({ status: "error", message: String(error) }),
      );
    return () => {
      cancelled = true;
    };
  }, [storeIndex, category, state.period]);

  const readingListIndex = useMemo(() => new PaperIndex(readingList), [readingList]);
  const activeIndex =
    state.view === "reading-list" ? readingListIndex : load.status === "ready" ? load.index : null;

  const results: SearchResult[] = useMemo(
    () =>
      state.view === "graph" ? [] : (activeIndex?.search(query, state.filters, state.sort) ?? []),
    [state.view, activeIndex, query, state.filters, state.sort],
  );
  // The graph has its own settings panel: it ignores the list filters, not the search words.
  const graphPapers = useMemo(
    () =>
      state.view === "graph" && load.status === "ready"
        ? load.index
            .search(query, { ...NO_FILTERS, venue: state.filters.venue }, "newest")
            .map(({ paper }) => paper)
        : [],
    [state.view, load, query, state.filters.venue],
  );
  // Suggestions come from every loaded paper, so they do not vanish as filters narrow results.
  const authorSuggestions = useMemo(
    () => valueCounts(activeIndex?.all() ?? [], (paper) => paper.authors, SUGGESTION_SIZE),
    [activeIndex],
  );
  const venueCounts = useMemo(
    () =>
      valueCounts(
        activeIndex?.all() ?? [],
        (paper) => (paper.venue ? [paper.venue] : []),
        SUGGESTION_SIZE,
      ),
    [activeIndex],
  );
  const affiliationSuggestions = useMemo(
    () =>
      valueCounts(activeIndex?.all() ?? [], (paper) => paper.affiliations ?? [], SUGGESTION_SIZE),
    [activeIndex],
  );
  const hasSearchWords = parseQuery(query).text !== "";
  const subjects = useMemo(
    () =>
      facetCounts(
        results,
        (paper) => (paper.primary_subject ? [paper.primary_subject] : []),
        FACET_SIZE,
      ),
    [results],
  );

  const savedIds = useMemo(
    () => new Set(readingList.map((paper) => paper.arxiv_id)),
    [readingList],
  );
  const toggleSaved = (paper: Paper) => {
    setReadingList((current) => {
      const next = current.some((saved) => saved.arxiv_id === paper.arxiv_id)
        ? current.filter((saved) => saved.arxiv_id !== paper.arxiv_id)
        : [paper, ...current];
      saveReadingList(next);
      return next;
    });
  };

  const lastUpdate = storeIndex ? formatDay(storeIndex.generated_at) : null;
  const toggleAbstracts = () => {
    setShowAbstracts(!showAbstracts);
    saveShowAbstracts(!showAbstracts);
  };

  const topbar = (
    <header class="topbar">
      <div class="topbar__brand">
        <h1>Preprint Radar</h1>
        {lastUpdate && <span class="muted">Updated {lastUpdate}</span>}
      </div>
      <nav class="tabs" aria-label="Views">
        <button
          type="button"
          class={`tab${state.view === "papers" ? " tab--active" : ""}`}
          onClick={() => update({ view: "papers" })}
        >
          Papers
        </button>
        <button
          type="button"
          class={`tab${state.view === "graph" ? " tab--active" : ""}`}
          onClick={() => update({ view: "graph" })}
        >
          Graph
        </button>
        <button
          type="button"
          class={`tab${state.view === "reading-list" ? " tab--active" : ""}`}
          onClick={() => update({ view: "reading-list" })}
        >
          Reading list ({readingList.length})
        </button>
      </nav>
    </header>
  );

  if (state.view === "graph") {
    return (
      <div class="layout layout--graph">
        {topbar}
        <GraphView
          papers={graphPapers}
          notice={
            load.status === "loading"
              ? "Loading papers…"
              : load.status === "error"
                ? `Could not load papers: ${load.message}`
                : null
          }
          categories={categories}
          category={category ?? ""}
          onCategory={(value) => update({ category: value })}
          storeDays={storeDays}
          period={state.period}
          onPeriod={(period) => update({ period })}
          query={state.query}
          onQuery={(value) => update({ query: value })}
          venues={venueCounts}
          venue={state.filters.venue}
          onVenue={(venue) => setFilters({ ...state.filters, venue })}
          onShowPapers={(kind, label) =>
            update({
              view: "papers",
              filters: {
                ...NO_FILTERS,
                venue: state.filters.venue,
                [kind === "institution" ? "affiliation" : "author"]: label,
              },
            })
          }
        />
      </div>
    );
  }

  return (
    <div class="layout">
      {topbar}

      <div class="search">
        <input
          type="search"
          class="search__input"
          placeholder="Search papers…"
          value={state.query}
          onInput={(event) => update({ query: event.currentTarget.value })}
          aria-label="Search papers"
          autofocus
        />
        <p class="search__hint muted">
          Searches titles, abstracts, authors and affiliations. <code>"neural radiance field"</code>{" "}
          in quotes finds that exact phrase; <code>-survey</code> leaves out the papers that contain
          the word.
        </p>
      </div>

      <div class="content">
        {category && (
          <Sidebar
            categories={categories}
            category={category}
            days={storeDays}
            period={state.period}
            filters={state.filters}
            authors={authorSuggestions}
            affiliations={affiliationSuggestions}
            venues={venueCounts}
            subjects={subjects}
            onCategory={(value) => update({ category: value })}
            onPeriod={(period) => update({ period })}
            onFilters={setFilters}
          />
        )}

        <main class="results">
          <div class="results__header">
            <p class="muted" aria-live="polite">
              {state.view === "reading-list"
                ? `${results.length} of ${readingList.length} saved papers`
                : load.status === "ready"
                  ? `${results.length} of ${load.index.size} papers`
                  : load.status === "loading"
                    ? "Loading papers…"
                    : null}
            </p>
            {hasSearchWords && (
              <fieldset class="segmented">
                <legend class="visually-hidden">Sort results</legend>
                <button
                  type="button"
                  class={`segmented__option${state.sort === "relevance" ? " segmented__option--active" : ""}`}
                  aria-pressed={state.sort === "relevance"}
                  title={RELEVANCE_HELP}
                  onClick={() => update({ sort: "relevance" })}
                >
                  Relevance
                </button>
                <button
                  type="button"
                  class={`segmented__option${state.sort === "newest" ? " segmented__option--active" : ""}`}
                  aria-pressed={state.sort === "newest"}
                  onClick={() => update({ sort: "newest" })}
                >
                  Newest
                </button>
                <button
                  type="button"
                  class="help"
                  aria-expanded={showRelevanceHelp}
                  aria-label="How is relevance computed?"
                  title={RELEVANCE_HELP}
                  onClick={() => setShowRelevanceHelp(!showRelevanceHelp)}
                >
                  ?
                </button>
              </fieldset>
            )}
            {state.view === "papers" && (
              <label class="toggle results__abstracts">
                <input type="checkbox" checked={showAbstracts} onChange={toggleAbstracts} />
                Show abstracts
              </label>
            )}
            {state.view === "reading-list" && readingList.length > 0 && (
              <div class="results__actions">
                <button
                  type="button"
                  class="button"
                  onClick={() =>
                    download("reading-list.bib", toBibtexFile(readingList), "application/x-bibtex")
                  }
                >
                  Export BibTeX
                </button>
                <button
                  type="button"
                  class="button"
                  onClick={() =>
                    download(
                      "reading-list.json",
                      JSON.stringify(readingList, null, 2),
                      "application/json",
                    )
                  }
                >
                  Export JSON
                </button>
              </div>
            )}
          </div>

          {hasSearchWords && showRelevanceHelp && <p class="help-note">{RELEVANCE_HELP}</p>}

          {load.status === "error" && state.view === "papers" ? (
            <p class="notice notice--error">Could not load papers: {load.message}</p>
          ) : state.view === "reading-list" && readingList.length === 0 ? (
            <p class="notice">
              Your reading list is empty. Use ☆ on a paper to save it; the list is kept in this
              browser.
            </p>
          ) : (
            <PaperList
              results={results}
              showAbstracts={showAbstracts || state.view === "reading-list"}
              savedIds={savedIds}
              onToggleSaved={toggleSaved}
              onAuthor={(author) => setFilters({ ...state.filters, author })}
              onAffiliation={(affiliation) => setFilters({ ...state.filters, affiliation })}
            />
          )}
        </main>
      </div>

      <footer class="site-footer muted">
        Data from <a href="https://arxiv.org">arXiv</a>, refreshed every weekday. Thank you to arXiv
        for use of its open access interoperability. This project is not affiliated with arXiv.
      </footer>
    </div>
  );
}
