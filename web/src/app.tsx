import { useCallback, useMemo, useState } from "preact/hooks";
import { toBibtexFile } from "./bibtex";
import { GraphView } from "./components/GraphView";
import { PaperList } from "./components/PaperList";
import { Sidebar } from "./components/Sidebar";
import { download } from "./download";
import { formatDay } from "./format";
import { useCitations } from "./hooks/use-citations";
import { usePapers } from "./hooks/use-papers";
import { useReadingList } from "./hooks/use-reading-list";
import { useTheme } from "./hooks/use-theme";
import { useUrlState } from "./hooks/use-url-state";
import { between } from "./period";
import { loadShowAbstracts, saveShowAbstracts, type ThemePreference } from "./preferences";
import {
  alphabetical,
  byCitations,
  facetCounts,
  NO_FILTERS,
  parseQuery,
  type SearchResult,
  valueCounts,
} from "./search";
import type { Paper } from "./types";
import { DEFAULT_STATE, writeState } from "./url-state";

const FACET_SIZE = 12;
const SUGGESTION_SIZE = 300;
const THEME_ICONS: Record<ThemePreference, string> = { auto: "◐", light: "☀", dark: "☾" };
const RELEVANCE_HELP =
  "Relevance ranks papers by how well they match your search words. Rarer words weigh more, " +
  "and a match counts most in the title, then in authors, affiliations, the abstract and " +
  "comments. Exact words count more than partial or approximate ones.";

export function App() {
  const { state, query, update, setFilters } = useUrlState();
  const cited = state.view === "cited";
  const { categories, category, storeDays, archiveYears, archiveYear, load, generatedAt } =
    usePapers(state.category, state.period, cited ? { year: state.year } : null);
  const citations = useCitations(category);
  const citationsNote =
    citations.source && citations.asOf
      ? `Citations on ${citations.source}, as of ${formatDay(citations.asOf)}`
      : undefined;
  const readingList = useReadingList();
  const { theme, resolved, next, cycle } = useTheme();
  const [showAbstracts, setShowAbstracts] = useState(loadShowAbstracts);
  const [showRelevanceHelp, setShowRelevanceHelp] = useState(false);

  const activeIndex =
    state.view === "reading-list" ? readingList.index : load.status === "ready" ? load.index : null;

  const results: SearchResult[] = useMemo(() => {
    if (state.view === "graph") return [];
    const found = activeIndex?.search(query, state.filters, cited ? "newest" : state.sort) ?? [];
    // The highly cited view ranks by citations; search words only narrow it down.
    return cited ? byCitations(found, citations.counts) : found;
  }, [state.view, cited, activeIndex, query, state.filters, state.sort, citations]);
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
  // Suggestions come from every loaded paper, so they do not vanish as filters narrow
  // results; the most frequent values are kept, then listed alphabetically.
  const authorSuggestions = useMemo(
    () =>
      alphabetical(
        valueCounts(activeIndex?.all() ?? [], (paper) => paper.authors, SUGGESTION_SIZE),
      ),
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
      alphabetical(
        valueCounts(activeIndex?.all() ?? [], (paper) => paper.affiliations ?? [], SUGGESTION_SIZE),
      ),
    [activeIndex],
  );
  const hasSearchWords = parseQuery(query).text !== "";
  // Day headings need results in announcement order (see search): no words, or newest.
  const groupByDay = !cited && (!hasSearchWords || state.sort === "newest");
  // A share link opens the paper on its own day, free of the sharer's search context.
  const linkTo = (paper: Paper) =>
    writeState({
      ...DEFAULT_STATE,
      category: category ?? null,
      period: between(paper.announced, paper.announced),
      paper: paper.arxiv_id,
    });
  const subjects = useMemo(
    () =>
      facetCounts(
        results,
        (paper) => (paper.primary_subject ? [paper.primary_subject] : []),
        FACET_SIZE,
      ),
    [results],
  );

  const lastUpdate = generatedAt ? formatDay(generatedAt) : null;
  // The graph shows the loaded period; a saved paper from another day brings its own.
  const showInGraph = (paper: Paper) =>
    update({
      view: "graph",
      paper: paper.arxiv_id,
      ...(load.status === "ready" && load.index.has(paper.arxiv_id)
        ? {}
        : { period: between(paper.announced, paper.announced) }),
    });
  const clearPaper = useCallback(() => update({ paper: null }), [update]);
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
      <div class="topbar__tools">
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
            class={`tab${cited ? " tab--active" : ""}`}
            title="The most cited papers older than a year, by year of first version"
            onClick={() => update({ view: "cited" })}
          >
            Highly cited
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
            Reading list ({readingList.papers.length})
          </button>
        </nav>
        <button
          type="button"
          class="icon-button"
          title={`Theme: ${theme} — click for ${next}`}
          aria-label={`Theme: ${theme}. Switch to ${next}.`}
          onClick={cycle}
        >
          {THEME_ICONS[theme]}
        </button>
      </div>
    </header>
  );

  if (state.view === "graph") {
    return (
      <div class="layout layout--graph">
        {topbar}
        <GraphView
          papers={graphPapers}
          citations={citations.counts}
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
          theme={resolved}
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
          focusPaper={state.paper}
          onFocusPaperLeft={clearPaper}
          onOpenPaper={(paper) =>
            update({
              view: "papers",
              query: "",
              filters: NO_FILTERS,
              period: between(paper.announced, paper.announced),
              paper: paper.arxiv_id,
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
            archive={
              cited
                ? { years: archiveYears, year: archiveYear, onYear: (year) => update({ year }) }
                : undefined
            }
          />
        )}

        <main class="results">
          <div class="results__header">
            <p class="muted" aria-live="polite">
              {state.view === "reading-list"
                ? `${results.length} of ${readingList.papers.length} saved papers`
                : cited && load.status === "ready" && archiveYear !== null
                  ? `${results.length} of ${load.index.size} highly cited papers first published in ${archiveYear}`
                  : load.status === "ready"
                    ? `${results.length} of ${load.index.size} papers`
                    : load.status === "loading"
                      ? "Loading papers…"
                      : null}
            </p>
            {hasSearchWords && !cited && (
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
            {state.view === "reading-list" && readingList.papers.length > 0 && (
              <div class="results__actions">
                <button
                  type="button"
                  class="button"
                  onClick={() =>
                    download(
                      "reading-list.bib",
                      toBibtexFile(readingList.papers),
                      "application/x-bibtex",
                    )
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
                      JSON.stringify(readingList.papers, null, 2),
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

          {load.status === "error" && (state.view === "papers" || cited) ? (
            <p class="notice notice--error">Could not load papers: {load.message}</p>
          ) : cited && archiveYears.length === 0 ? (
            <p class="notice">
              The archive of highly cited papers is built weekly, from citation counts: it is not
              there yet.
            </p>
          ) : state.view === "reading-list" && readingList.papers.length === 0 ? (
            <p class="notice">
              Your reading list is empty. Use ☆ on a paper to save it; the list is kept in this
              browser.
            </p>
          ) : (
            <>
              {state.view === "papers" &&
                state.paper &&
                load.status === "ready" &&
                !load.index.has(state.paper) && (
                  <p class="notice">
                    This paper is not among the stored papers of this period (it may be older than
                    the papers kept).{" "}
                    <a href={`https://arxiv.org/abs/${state.paper}`}>See it on arXiv</a>.
                  </p>
                )}
              <PaperList
                results={results}
                groupByDay={groupByDay}
                openId={state.paper}
                linkTo={linkTo}
                onOpenPaper={(arxivId) => update({ paper: arxivId })}
                // The graph is built from the days kept in full, not from the archive.
                onShowInGraph={cited ? undefined : showInGraph}
                citations={citations.counts}
                citationsNote={citationsNote}
                showAbstracts={showAbstracts || state.view === "reading-list"}
                savedIds={readingList.savedIds}
                onToggleSaved={readingList.toggle}
                onAuthor={(author) => setFilters({ ...state.filters, author })}
                onAffiliation={(affiliation) => setFilters({ ...state.filters, affiliation })}
              />
            </>
          )}
        </main>
      </div>

      <footer class="site-footer muted">
        Data from <a href="https://arxiv.org">arXiv</a>, refreshed every weekday. Thank you to arXiv
        for use of its open access interoperability. This project is not affiliated with arXiv.
        Citation counts from <a href="https://www.semanticscholar.org">Semantic Scholar</a>,
        institutions from the <a href="https://ror.org">Research Organization Registry</a> and{" "}
        <a href="https://openalex.org">OpenAlex</a>.
      </footer>
    </div>
  );
}
