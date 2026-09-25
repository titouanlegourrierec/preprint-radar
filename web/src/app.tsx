import { useEffect, useMemo, useState } from "preact/hooks";
import { toBibtexFile } from "./bibtex";
import { ActiveFilters } from "./components/ActiveFilters";
import { PaperList } from "./components/PaperList";
import { Sidebar } from "./components/Sidebar";
import { loadDays, loadIndex } from "./data";
import { loadReadingList, saveReadingList } from "./reading-list";
import { facetCounts, PaperIndex, type SearchFilters, type SearchResult } from "./search";
import type { Paper, StoreIndex } from "./types";
import { RANGES, readState, type ViewState, writeState } from "./url-state";

const SEARCH_DEBOUNCE_MS = 150;
const FACET_SIZE = 12;

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

  useEffect(() => {
    if (!storeIndex || !category) return;
    const days = (storeIndex.categories[category] ?? []).slice(0, RANGES[state.range].days);
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
  }, [storeIndex, category, state.range]);

  const readingListIndex = useMemo(() => new PaperIndex(readingList), [readingList]);
  const activeIndex =
    state.view === "reading-list" ? readingListIndex : load.status === "ready" ? load.index : null;

  const results: SearchResult[] = useMemo(
    () => activeIndex?.search(query, state.filters, state.sort) ?? [],
    [activeIndex, query, state.filters, state.sort],
  );
  const affiliations = useMemo(
    () => facetCounts(results, (paper) => paper.affiliations ?? [], FACET_SIZE),
    [results],
  );
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

  const lastUpdate = storeIndex ? new Date(storeIndex.generated_at).toLocaleString() : null;

  return (
    <div class="layout">
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
            class={`tab${state.view === "reading-list" ? " tab--active" : ""}`}
            onClick={() => update({ view: "reading-list" })}
          >
            Reading list ({readingList.length})
          </button>
        </nav>
      </header>

      <div class="search">
        <input
          type="search"
          class="search__input"
          placeholder='Search titles, abstracts, authors, affiliations… e.g. gaussian splatting "novel view" -survey'
          value={state.query}
          onInput={(event) => update({ query: event.currentTarget.value })}
          aria-label="Search papers"
          autofocus
        />
      </div>

      <div class="content">
        {category && (
          <Sidebar
            categories={categories}
            category={category}
            range={state.range}
            sort={state.sort}
            filters={state.filters}
            affiliations={affiliations}
            subjects={subjects}
            onCategory={(value) => update({ category: value })}
            onRange={(range) => update({ range })}
            onSort={(sort) => update({ sort })}
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

          <ActiveFilters filters={state.filters} onFilters={setFilters} />

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
