import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ALL_YEARS, oneYear, publishedIn } from "./archive-years";
import { toBibtexFile } from "./bibtex";
import { About } from "./components/About";
import { ActiveFilters } from "./components/ActiveFilters";
import { GraphView } from "./components/GraphView";
import { PaperList } from "./components/PaperList";
import { Rankings } from "./components/Rankings";
import { SavedSearches } from "./components/SavedSearches";
import { Sidebar } from "./components/Sidebar";
import { download } from "./download";
import { toCsv, toMarkdown, toRis } from "./export";
import { feedOf } from "./feeds";
import {
  categoryName,
  countOf,
  citationsNote as formatCitationsNote,
  formatDay,
  gainLabel,
  seenHidden,
} from "./format";
import { useCitations } from "./hooks/use-citations";
import { usePapers } from "./hooks/use-papers";
import { useReadingList } from "./hooks/use-reading-list";
import { useSavedSearches } from "./hooks/use-saved-searches";
import { useTheme } from "./hooks/use-theme";
import { useTriage } from "./hooks/use-triage";
import { useUrlState } from "./hooks/use-url-state";
import { namedInstitutions } from "./institutions";
import { hasModifier, isTyping } from "./keyboard";
import { between, LONGEST_RANGE, PAPER_BUDGET, samePeriod, selectDays } from "./period";
import { loadShowAbstracts, saveShowAbstracts, type ThemePreference } from "./preferences";
import { readingListFile } from "./reading-list";
import { searchOf } from "./saved-searches";
import {
  activeFilterCount,
  alphabetical,
  arxivIdOf,
  byCitations,
  byGains,
  exactly,
  facetCounts,
  mostlyTied,
  NO_FILTERS,
  nameHighlights,
  parseQuery,
  type SearchResult,
  valueCounts,
} from "./search";
import { searchKey } from "./text";
import type { Paper } from "./types";
import { archiveYearOf, listKey, paperLink, type ViewState, writeState } from "./url-state";
import { venueFacets } from "./venues";

const FACET_SIZE = 12;
// The exports of the results shown, as files.
const EXPORTS: {
  label: string;
  file: string;
  type: string;
  render: (papers: Paper[], citations: ReadonlyMap<string, number>) => string;
}[] = [
  {
    label: "BibTeX",
    file: "papers.bib",
    type: "application/x-bibtex",
    render: (papers) => toBibtexFile(papers),
  },
  { label: "CSV", file: "papers.csv", type: "text/csv", render: toCsv },
  {
    label: "RIS",
    file: "papers.ris",
    type: "application/x-research-info-systems",
    render: (papers) => toRis(papers),
  },
  {
    label: "Markdown",
    file: "papers.md",
    type: "text/markdown",
    render: (papers) => toMarkdown(papers),
  },
];

// What each view shows, said once at its top: the tabs' tooltips are out of reach on touch.
const VIEW_NOTES: Partial<Record<ViewState["view"], string>> = {
  cited: "The most cited papers older than a year, by year of first version.",
  rankings: "Institutions and authors of the papers shown, by papers or citations.",
  "reading-list": "The papers you saved with ☆, kept in this browser.",
};
const VIEW_TITLES: Record<ViewState["view"], string> = {
  papers: "",
  cited: "Highly cited",
  graph: "Graph",
  rankings: "Rankings",
  "reading-list": "Reading list",
  about: "About",
};
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
  const {
    categories,
    category,
    storeDays,
    archiveYears,
    archiveRange,
    archiveLeftOut,
    load,
    searchable,
    retry,
    generatedAt,
  } = usePapers(state.category, state.period, archived ? { years: state.year } : null);
  const readingList = useReadingList(load.status === "ready" ? load.index : null);
  const shownPapers = useMemo(
    () => [...(load.status === "ready" ? load.index.all() : []), ...readingList.papers],
    [load, readingList.papers],
  );
  const citations = useCitations(category, shownPapers, storeDays.at(-1)?.date);
  const citationsNote =
    citations.source && citations.asOf
      ? formatCitationsNote(citations.source, citations.asOf)
      : undefined;
  const importInput = useRef<HTMLInputElement>(null);
  const triage = useTriage(category ?? null, storeDays);

  const savedSearches = useSavedSearches();
  const searchInput = useRef<HTMLInputElement>(null);

  // "/" jumps to the search box, but in the graph, whose own search box takes it.
  useEffect(() => {
    if (state.view === "graph") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "/" ||
        event.defaultPrevented ||
        hasModifier(event) ||
        isTyping(event.target)
      )
        return;
      event.preventDefault();
      searchInput.current?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [state.view]);
  const { theme, resolved, next, cycle } = useTheme();
  const [showAbstracts, setShowAbstracts] = useState(loadShowAbstracts);
  const [showRelevanceHelp, setShowRelevanceHelp] = useState(false);

  const activeIndex =
    state.view === "reading-list" ? readingList.index : load.status === "ready" ? load.index : null;

  // The tab's title says what is shown: a paper, a search, or the view.
  const focusedTitle = state.paper ? activeIndex?.get(state.paper)?.title : undefined;
  useEffect(() => {
    const label = focusedTitle ?? (query.trim() || VIEW_TITLES[state.view]);
    document.title = label ? `${label} · Preprint Radar` : "Preprint Radar";
  }, [focusedTitle, query, state.view]);

  const triaged = state.view === "papers";
  const hiding = triaged && triage.hideSeen && triage.seen.size > 0;
  // The highly cited view ranks by citations; search words only narrow it down. Rising
  // papers come before, by what they gained in a week (none known: by citations alone).
  const byCount = cited || state.sort === "citations" || state.sort === "rising";
  // In three steps, each redone only when what it reads changes (UX-23): marking a paper
  // seen does not search again, nor do late counts when the order ignores them.
  const found = useMemo(
    () =>
      state.view === "graph"
        ? []
        : (activeIndex?.search(query, state.filters, cited ? "newest" : state.sort) ?? []),
    [state.view, cited, activeIndex, query, state.filters, state.sort],
  );
  const hiddenSeen = hiding ? triage.seen : null;
  const shown = useMemo(
    () => (hiddenSeen ? found.filter(({ paper }) => !hiddenSeen.has(paper.arxiv_id)) : found),
    [found, hiddenSeen],
  );
  // Papers that Hide seen leaves out, which the count and an empty list say.
  const hiddenCount = found.length - shown.length;
  const rankingCounts = byCount ? citations.counts : null;
  const rankingGains = state.sort === "rising" ? citations.gains : null;
  const results: SearchResult[] = useMemo(() => {
    if (rankingGains && rankingCounts) return byGains(shown, rankingGains, rankingCounts);
    return rankingCounts ? byCitations(shown, rankingCounts) : shown;
  }, [shown, rankingCounts, rankingGains]);
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
    () => venueFacets(activeIndex?.all() ?? [], SUGGESTION_SIZE),
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
  const groupByDay = !byCount && (!hasSearchWords || state.sort === "newest");
  // Without search words, relevance is the announcement order.
  const newest = state.sort === "newest" || (state.sort === "relevance" && !hasSearchWords);
  // Rising papers, once two weekly refreshes of the counts are known (CIT-9).
  const gainsSpan = citations.gainsSpan;
  const rising = state.sort === "rising" && gainsSpan !== null;
  const nameTerms = useMemo(() => nameHighlights(state.filters), [state.filters]);
  // The feed of the institution or major venue the papers are filtered on (§17.1 #6).
  const feedInstitution = state.view === "papers" ? state.filters.affiliation : null;
  const feedKnown = useMemo(() => {
    if (!(feedInstitution?.exact && load.status === "ready")) return false;
    const key = searchKey(feedInstitution.text);
    return load.index
      .all()
      .some((paper) => namedInstitutions(paper).some((name) => searchKey(name) === key));
  }, [feedInstitution, load]);
  const feed =
    state.view === "papers" && category ? feedOf(category, state.filters, () => feedKnown) : null;
  const gainOf = (arxivId: string) => {
    const gain = citations.gains.get(arxivId);
    return gain && gainsSpan ? gainLabel(gain, gainsSpan, citations.source) : undefined;
  };
  // A share link opens the paper on its own day, free of the sharer's search context.
  const pastedId = arxivIdOf(query);
  // "No paper matches" offers the longest preset when it holds more days than the period.
  const longestPeriod = { kind: "recent", range: LONGEST_RANGE } as const;
  const longestDays = selectDays(storeDays, longestPeriod).length;
  const widerPeriod = longestDays > selectDays(storeDays, state.period).length;
  const sinceLastVisit = triage.sinceLastVisit && {
    ...triage.sinceLastVisit,
    period: between(triage.sinceLastVisit.from, triage.sinceLastVisit.to),
  };
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
  const archiveAsOf = generatedAt ? new Date(generatedAt) : undefined;
  // The graph shows the loaded papers; a saved paper from elsewhere brings its day, or
  // its archive year when it is older than the days kept.
  const showInGraph = (paper: Paper) => {
    const loaded = load.status === "ready" && load.index.has(paper.arxiv_id);
    const year = archiveYearOf(paper.announced, oldestDay, yearsArchived);
    if (loaded) {
      update({ view: "graph", paper: paper.arxiv_id, year: archived ? archiveRange : null });
    } else if (year !== null) {
      update({ view: "graph", paper: paper.arxiv_id, year: oneYear(year) });
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
  // A tab leaves the graph's focus behind (`update` does too): it is the graph's alone.
  const tab = (active: boolean, patch: Partial<ViewState>) => ({
    href: `./${writeState({ ...state, query, paper: null, focus: null, ...patch })}`,
    "aria-current": active ? ("page" as const) : undefined,
    onClick: (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      event.preventDefault();
      update(patch);
    },
  });

  const skipLink = (
    <a class="skip-link" href="#main">
      Skip to {state.view === "graph" ? "the graph" : "the content"}
    </a>
  );

  const topbar = (
    <header class="topbar">
      <div class="topbar__brand">
        <h1>Preprint Radar</h1>
        {category && <span class="topbar__category">{categoryName(category)}</span>}
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
              ...(cited ? { year: archiveRange } : {}),
            })}
          >
            Graph
          </a>
          <a
            class={`tab${rankings ? " tab--active" : ""}`}
            title="Institutions and authors of the papers shown, by papers or citations"
            {...tab(rankings, { view: "rankings", ...(cited ? { year: archiveRange } : {}) })}
          >
            Rankings
          </a>
          <a
            class={`tab${state.view === "reading-list" ? " tab--active" : ""}`}
            {...tab(state.view === "reading-list", { view: "reading-list" })}
          >
            Reading list ({readingList.papers.length.toLocaleString()})
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
        {skipLink}
        {topbar}
        <About />
        {footer}
      </div>
    );
  }

  if (state.view === "graph") {
    return (
      <div class="layout layout--graph">
        {skipLink}
        {topbar}
        <GraphView
          papers={graphPapers}
          citations={citations.counts}
          focus={state.focus}
          onFocus={(focus) => update({ focus })}
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
          archiveRange={archived ? archiveRange : null}
          onArchiveRange={(year) => update({ year })}
          query={state.query}
          onQuery={(value) => update({ query: value })}
          venues={venueCounts}
          venue={state.filters.venue}
          onVenue={(venue) => setFilters({ ...state.filters, venue })}
          theme={resolved}
          // A graph of archive years lists its papers in Highly cited, over the same years: the
          // Papers view would load the recent days instead.
          onShowPapers={(kind, label) =>
            update({
              view: archived ? "cited" : "papers",
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
            update(
              archived
                ? { view: "cited", query: "", filters: NO_FILTERS, paper: paper.arxiv_id }
                : {
                    view: "papers",
                    query: "",
                    filters: NO_FILTERS,
                    period: between(paper.announced, paper.announced),
                    paper: paper.arxiv_id,
                  },
            )
          }
        />
      </div>
    );
  }

  return (
    <div class="layout">
      {skipLink}
      {topbar}

      <div class="search">
        <input
          type="search"
          class="search__input"
          ref={searchInput}
          placeholder="Search papers…"
          value={state.query}
          onInput={(event) => update({ query: event.currentTarget.value })}
          aria-label="Search papers"
          aria-describedby="search-hint"
          // No autofocus: j and k would type into the box. "/" comes here, Escape leaves.
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            // Leave the box, keeping its words (a search box clears them on Escape).
            event.preventDefault();
            event.currentTarget.blur();
          }}
        />
      </div>
      {/* Outside the sticky bar, which then stays short and hides no focused control. */}
      <p id="search-hint" class="search__hint muted">
        Searches titles, abstracts, authors, affiliations, venues and comments, or an arXiv id.{" "}
        <code>"neural radiance field"</code> in quotes finds that exact phrase; <code>-survey</code>{" "}
        leaves out the papers that contain the word.
      </p>

      <div class="content">
        {category && (
          <Sidebar
            categories={categories}
            category={category}
            asOf={archiveAsOf}
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
                ? {
                    years: archiveYears,
                    range: archiveRange ?? ALL_YEARS,
                    onRange: (year) => update({ year }),
                  }
                : undefined
            }
            source={
              rankings
                ? {
                    years: archiveYears,
                    range: archived ? archiveRange : null,
                    onRange: (year) => update({ year }),
                  }
                : undefined
            }
          >
            {triaged && (
              <SavedSearches
                searches={savedSearches.searches}
                // Counted once the index is built, so that the list never waits for it.
                index={searchable}
                since={triage.previousVisit}
                current={{ query, filters: state.filters }}
                onSave={() => savedSearches.save({ query, filters: state.filters })}
                onRemove={savedSearches.remove}
                onOpen={(saved, onlyNew) =>
                  update({
                    ...searchOf(saved),
                    ...(onlyNew && sinceLastVisit ? { period: sinceLastVisit.period } : {}),
                  })
                }
              />
            )}
          </Sidebar>
        )}

        <main class="results" id="main">
          <div class="results__header">
            <p class="muted" aria-live="polite">
              {state.view === "reading-list"
                ? `${results.length.toLocaleString()} of ${countOf(readingList.papers.length, "saved paper")}`
                : archived && load.status === "ready" && archiveRange !== null
                  ? `${results.length.toLocaleString()} of ${countOf(load.index.size, `highly cited ${category ?? ""} paper`)} first published ${publishedIn(archiveRange, archiveYears, archiveAsOf)}`
                  : load.status === "ready"
                    ? `${results.length.toLocaleString()} of ${countOf(load.index.size, `${category ?? ""} paper`)}${hiddenCount > 0 ? ` · ${seenHidden(hiddenCount).count}` : ""}`
                    : load.status === "loading"
                      ? "Loading papers…"
                      : null}
            </p>
            {(state.view === "papers" || state.view === "reading-list" || (cited && gainsSpan)) && (
              <fieldset class="segmented">
                <legend class="visually-hidden">Sort results</legend>
                {hasSearchWords && !cited && (
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
                {!cited && (
                  <button
                    type="button"
                    class={`segmented__option${newest ? " segmented__option--active" : ""}`}
                    aria-pressed={newest}
                    onClick={() => update({ sort: "newest" })}
                  >
                    Newest
                  </button>
                )}
                <button
                  type="button"
                  class={`segmented__option${byCount && !rising ? " segmented__option--active" : ""}`}
                  aria-pressed={byCount && !rising}
                  title={citationsNote}
                  onClick={() => update({ sort: "citations" })}
                >
                  Most cited
                </button>
                {gainsSpan && (
                  <button
                    type="button"
                    class={`segmented__option${rising ? " segmented__option--active" : ""}`}
                    aria-pressed={rising}
                    title={`By the citations gained between ${formatDay(gainsSpan.since)} and ${formatDay(gainsSpan.to)}`}
                    onClick={() => update({ sort: "rising" })}
                  >
                    Rising
                  </button>
                )}
                {hasSearchWords && !cited && (
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
              <div class="results__toggles">
                <label class="toggle">
                  <input
                    type="checkbox"
                    checked={triage.hideSeen}
                    onChange={triage.toggleHideSeen}
                  />
                  Hide seen
                </label>
                <label class="toggle">
                  <input type="checkbox" checked={showAbstracts} onChange={toggleAbstracts} />
                  Show abstracts
                </label>
              </div>
            )}
            {(state.view === "papers" || cited) && results.length > 0 && (
              <details class="export-menu">
                <summary class="button export-menu__toggle">
                  Export {results.length.toLocaleString()}
                </summary>
                <div class="export-menu__items">
                  {EXPORTS.map(({ label, file, type, render }) => (
                    <button
                      key={label}
                      type="button"
                      class="link-button"
                      onClick={() =>
                        download(
                          file,
                          render(
                            results.map(({ paper }) => paper),
                            citations.counts,
                          ),
                          type,
                        )
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </details>
            )}
            {state.view === "reading-list" && (
              <div class="results__actions">
                <button type="button" class="button" onClick={() => importInput.current?.click()}>
                  Import
                </button>
                <input
                  ref={importInput}
                  type="file"
                  accept="application/json,.json"
                  hidden
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    if (file) {
                      void readingList.importFile(file, (value) => {
                        const added = savedSearches.importSearches(value);
                        return added
                          ? `${added} saved search${added === 1 ? "" : "es"} added`
                          : null;
                      });
                    }
                    event.currentTarget.value = "";
                  }}
                />
              </div>
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
                      JSON.stringify(
                        readingListFile(readingList.papers, savedSearches.searches),
                        null,
                        2,
                      ),
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

          {state.view === "reading-list" && readingList.message && (
            <p class="notice notice--new" role="status">
              {readingList.message}{" "}
              <button type="button" class="link-button" onClick={readingList.dismissMessage}>
                Dismiss
              </button>
            </p>
          )}

          {triaged && sinceLastVisit && !samePeriod(state.period, sinceLastVisit.period) && (
            <p class="notice notice--new">
              {countOf(sinceLastVisit.papers, "new paper")} since your last visit.{" "}
              <button
                type="button"
                class="link-button"
                onClick={() => update({ period: sinceLastVisit.period })}
              >
                {sinceLastVisit.papers > PAPER_BUDGET
                  ? `Show the latest ${PAPER_BUDGET.toLocaleString()}`
                  : "Show them"}
              </button>
            </p>
          )}
          {triaged && load.status === "ready" && (
            <p class="shortcuts muted">
              Keys: <kbd>j</kbd> <kbd>k</kbd> move, <kbd>o</kbd> open, <kbd>s</kbd> save,{" "}
              <kbd>x</kbd> seen, <kbd>/</kbd> search, <kbd>Esc</kbd> leave the search.
            </p>
          )}

          {archiveLeftOut > 0 && load.status === "ready" && (
            <p class="help-note">
              These years hold {(load.index.size + archiveLeftOut).toLocaleString()} papers: the{" "}
              {load.index.size.toLocaleString()} best ranked by citations per year of age are shown,
              as many as a period loads. Narrow the years for the {archiveLeftOut.toLocaleString()}{" "}
              others.
            </p>
          )}
          {VIEW_NOTES[state.view] && (
            <p class="view-note muted">
              {VIEW_NOTES[state.view]}
              {cited &&
                ` Chosen every week by citations per year of age, among the papers first published more than 12 months ago.${citationsNote ? ` ${citationsNote}.` : ""}`}
            </p>
          )}
          {byCount &&
            !rising &&
            state.view !== "rankings" &&
            mostlyTied(results, citations.counts) && (
              <p class="help-note">
                Most of these papers have the same number of citations (often none yet, or not
                known): among them, the order is by relevance or date.
              </p>
            )}
          {state.view !== "rankings" && (
            <ActiveFilters filters={state.filters} onFilters={setFilters} />
          )}
          {feed && (
            <p class="feed-link muted">
              New papers {feed.kind === "venue" ? "accepted at" : "from"} {feed.name}, in a feed
              reader:{" "}
              <a href={encodeURI(feed.path)} type="application/atom+xml">
                Atom feed
              </a>
            </p>
          )}

          {load.status === "error" && state.view !== "reading-list" ? (
            <p class="notice notice--error" role="alert">
              Could not load the papers: {load.message}.{" "}
              <button type="button" class="link-button" onClick={retry}>
                Retry
              </button>
            </p>
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
                    the papers kept).
                    {/* An arXiv link only for an arXiv id: `?paper=` is anyone's text (SEC-7). */}
                    {arxivIdOf(state.paper) === state.paper && (
                      <>
                        {" "}
                        <a
                          href={`https://arxiv.org/abs/${state.paper}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          See it on arXiv
                        </a>
                        .
                      </>
                    )}
                  </p>
                )}
              {pastedId && results.length === 0 && hiddenCount === 0 && load.status === "ready" && (
                <p class="notice">
                  {pastedId} is not among the stored papers of this period.{" "}
                  <a
                    href={`https://arxiv.org/abs/${pastedId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    See it on arXiv
                  </a>
                  .
                </p>
              )}
              {results.length === 0 && hiddenCount > 0 && (
                <p class="notice">
                  {seenHidden(hiddenCount).empty}{" "}
                  <button type="button" class="link-button" onClick={triage.toggleHideSeen}>
                    Show seen papers
                  </button>
                </p>
              )}
              {!pastedId &&
                results.length === 0 &&
                hiddenCount === 0 &&
                (load.status === "ready" || state.view === "reading-list") &&
                activeIndex !== null &&
                activeIndex.size > 0 && (
                  <p class="notice">
                    No paper matches
                    {state.view === "papers" ? " in this period" : ""}.{" "}
                    {activeFilterCount(state.filters) > 0 && (
                      <button
                        type="button"
                        class="link-button"
                        onClick={() => setFilters(NO_FILTERS)}
                      >
                        Clear the filters
                      </button>
                    )}
                    {state.view === "papers" && widerPeriod && (
                      <>
                        {activeFilterCount(state.filters) > 0 && " · "}
                        <button
                          type="button"
                          class="link-button"
                          onClick={() => update({ period: longestPeriod })}
                        >
                          Search the last {longestDays} days
                        </button>
                      </>
                    )}
                  </p>
                )}
              <PaperList
                results={results}
                resetKey={listKey(state, query)}
                nameHighlights={nameTerms}
                groupByDay={groupByDay}
                openId={state.paper}
                linkTo={linkTo}
                onOpenPaper={(arxivId) => update({ paper: arxivId })}
                onClosePaper={() => update({ paper: null })}
                onShowInGraph={showInGraph}
                citations={citations.counts}
                citationsNote={citationsNote}
                gainOf={gainOf}
                showAbstracts={showAbstracts || state.view === "reading-list"}
                savedIds={readingList.savedIds}
                onToggleSaved={readingList.toggle}
                seenIds={triaged ? triage.seen : undefined}
                onToggleSeen={triaged ? triage.toggleSeen : undefined}
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
