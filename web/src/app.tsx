import { useCallback, useMemo, useState } from "preact/hooks";
import { toBibtexFile } from "./bibtex";
import { About } from "./components/About";
import { GraphView } from "./components/GraphView";
import { PaperList } from "./components/PaperList";
import { Rankings } from "./components/Rankings";
import { Sidebar } from "./components/Sidebar";
import { download } from "./download";
import { citationsNote as formatCitationsNote, formatDay } from "./format";
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
  exactly,
  facetCounts,
  NO_FILTERS,
  parseQuery,
  type SearchResult,
  valueCounts,
} from "./search";
import type { Paper } from "./types";
import { archiveYearOf, DEFAULT_STATE, paperLink, type ViewState, writeState } from "./url-state";

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
  const rankings = state.view === "rankings";
  // The highly cited view always shows the archive; the graph and rankings, given a year.
  const archived = cited || ((state.view === "graph" || rankings) && state.year !== null);
  const { categories, category, storeDays, archiveYears, archiveYear, load, generatedAt } =
    usePapers(state.category, state.period, archived ? { year: state.year } : null);
  const citations = useCitations(category);
  const citationsNote =
    citations.source && citations.asOf
      ? formatCitationsNote(citations.source, citations.asOf)
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
    return cited || state.sort === "citations" ? byCitations(found, citations.counts) : found;
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
  const rankedPapers = useMemo(
    () => (rankings ? results.map(({ paper }) => paper) : []),
    [rankings, results],
  );
  const hasSearchWords = parseQuery(query).text !== "";
  // Day headings need results in announcement order (see search): no words, or newest.
  const groupByDay =
    !cited && state.sort !== "citations" && (!hasSearchWords || state.sort === "newest");
  // Without search words, relevance is the announcement order.
  const newest = state.sort === "newest" || (state.sort === "relevance" && !hasSearchWords);
  // A share link opens the paper on its own day, free of the sharer's search context.
  const oldestDay = storeDays.at(-1)?.date;
  const yearsArchived = archiveYears.map((entry) => entry.year);
  const linkTo = (paper: Paper) =>
    paperLink(paper, { category: category ?? null, oldestDay, archiveYears: yearsArchived });
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
  // The graph shows the loaded papers; a saved paper from elsewhere brings its day, or
  // its archive year when it is older than the days kept.
  const showInGraph = (paper: Paper) => {
    const loaded = load.status === "ready" && load.index.has(paper.arxiv_id);
    const year = archiveYearOf(paper.announced, oldestDay, yearsArchived);
    if (loaded) {
      update({ view: "graph", paper: paper.arxiv_id, year: archived ? archiveYear : null });
    } else if (year !== null) {
      update({ view: "graph", paper: paper.arxiv_id, year });
    } else {
      update({
        view: "graph",
        paper: paper.arxiv_id,
        year: null,
        period: between(paper.announced, paper.announced),
      });
    }
  };
  const clearPaper = useCallback(() => update({ paper: null }), [update]);
  const toggleAbstracts = () => {
    setShowAbstracts(!showAbstracts);
    saveShowAbstracts(!showAbstracts);
  };

  // Tabs are links, so that they open in a new tab too; a plain click stays in the page.
  const tab = (active: boolean, patch: Partial<ViewState>) => ({
    href: `./${writeState({ ...state, query, paper: null, ...patch })}`,
    "aria-current": active ? ("page" as const) : undefined,
    onClick: (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      event.preventDefault();
      update(patch);
    },
  });

  const topbar = (
    <header class="topbar">
      <div class="topbar__brand">
        <h1>Preprint Radar</h1>
        {lastUpdate && <span class="muted">Updated {lastUpdate}</span>}
      </div>
      <div class="topbar__tools">
        <nav class="tabs" aria-label="Views">
          <a
            class={`tab${state.view === "papers" ? " tab--active" : ""}`}
            {...tab(state.view === "papers", { view: "papers", year: null })}
          >
            Papers
          </a>
          <a
            class={`tab${cited ? " tab--active" : ""}`}
            title="The most cited papers older than a year, by year of first version"
            {...tab(cited, { view: "cited" })}
          >
            Highly cited
          </a>
          <a
            class={`tab${state.view === "graph" ? " tab--active" : ""}`}
            // From the highly cited papers, the graph shows them.
            {...tab(state.view === "graph", {
              view: "graph",
              ...(cited ? { year: archiveYear } : {}),
            })}
          >
            Graph
          </a>
          <a
            class={`tab${rankings ? " tab--active" : ""}`}
            title="Institutions and authors of the papers shown, by papers or citations"
            {...tab(rankings, { view: "rankings", ...(cited ? { year: archiveYear } : {}) })}
          >
            Rankings
          </a>
          <a
            class={`tab${state.view === "reading-list" ? " tab--active" : ""}`}
            {...tab(state.view === "reading-list", { view: "reading-list" })}
          >
            Reading list ({readingList.papers.length})
          </a>
          <a
            class={`tab${state.view === "about" ? " tab--active" : ""}`}
            title="Where the data comes from, corrections and privacy"
            {...tab(state.view === "about", { view: "about" })}
          >
            About
          </a>
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

  const footer = (
    <footer class="site-footer muted">
      Data from <a href="https://arxiv.org">arXiv</a>, refreshed every weekday. Thank you to arXiv
      for use of its open access interoperability. This project is not affiliated with arXiv.
      Citation counts from <a href="https://www.semanticscholar.org">Semantic Scholar</a>,
      institutions from the <a href="https://ror.org">Research Organization Registry</a> and{" "}
      <a href="https://openalex.org">OpenAlex</a>.{" "}
      <a
        href="?view=about"
        onClick={(event) => {
          event.preventDefault();
          update({ view: "about" });
        }}
      >
        About the data, corrections and privacy
      </a>
      .
    </footer>
  );

  if (state.view === "about") {
    return (
      <div class="layout">
        {topbar}
        <About />
        {footer}
      </div>
    );
  }

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
          archiveYears={archiveYears}
          archiveYear={archived ? archiveYear : null}
          onArchiveYear={(year) => update({ year })}
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
                [kind === "institution" ? "affiliation" : "author"]: exactly(label),
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
            source={
              rankings
                ? {
                    years: archiveYears,
                    year: archived ? archiveYear : null,
                    onYear: (year) => update({ year }),
                  }
                : undefined
            }
          />
        )}

        <main class="results">
          <div class="results__header">
            <p class="muted" aria-live="polite">
              {state.view === "reading-list"
                ? `${results.length} of ${readingList.papers.length} saved papers`
                : archived && load.status === "ready" && archiveYear !== null
                  ? `${results.length} of ${load.index.size} highly cited papers first published in ${archiveYear}`
                  : load.status === "ready"
                    ? `${results.length} of ${load.index.size} papers`
                    : load.status === "loading"
                      ? "Loading papers…"
                      : null}
            </p>
            {(state.view === "papers" || state.view === "reading-list") && (
              <fieldset class="segmented">
                <legend class="visually-hidden">Sort results</legend>
                {hasSearchWords && (
                  <button
                    type="button"
                    class={`segmented__option${state.sort === "relevance" ? " segmented__option--active" : ""}`}
                    aria-pressed={state.sort === "relevance"}
                    title={RELEVANCE_HELP}
                    onClick={() => update({ sort: "relevance" })}
                  >
                    Relevance
                  </button>
                )}
                <button
                  type="button"
                  class={`segmented__option${newest ? " segmented__option--active" : ""}`}
                  aria-pressed={newest}
                  onClick={() => update({ sort: "newest" })}
                >
                  Newest
                </button>
                <button
                  type="button"
                  class={`segmented__option${state.sort === "citations" ? " segmented__option--active" : ""}`}
                  aria-pressed={state.sort === "citations"}
                  title={citationsNote}
                  onClick={() => update({ sort: "citations" })}
                >
                  Most cited
                </button>
                {hasSearchWords && (
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
                )}
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

          {load.status === "error" && state.view !== "reading-list" ? (
            <p class="notice notice--error">Could not load papers: {load.message}</p>
          ) : rankings ? (
            <Rankings
              papers={rankedPapers}
              citations={citations.counts}
              citationsNote={citationsNote}
              archived={archived}
              onEntity={(kind, name) =>
                update({
                  view: archived ? "cited" : "papers",
                  filters: {
                    ...state.filters,
                    [kind === "institution" ? "affiliation" : "author"]: exactly(name),
                  },
                })
              }
            />
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
                onShowInGraph={showInGraph}
                citations={citations.counts}
                citationsNote={citationsNote}
                showAbstracts={showAbstracts || state.view === "reading-list"}
                savedIds={readingList.savedIds}
                onToggleSaved={readingList.toggle}
                onAuthor={(author) => setFilters({ ...state.filters, author: exactly(author) })}
                onAffiliation={(affiliation) => setFilters({ ...state.filters, affiliation })}
              />
            </>
          )}
        </main>
      </div>

      {footer}
    </div>
  );
}
