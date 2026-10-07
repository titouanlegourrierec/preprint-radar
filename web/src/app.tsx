import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ALL_YEARS, oneYear, publishedIn } from "./archive-years";
import { About } from "./components/About";
import { ActiveFilters } from "./components/ActiveFilters";
import { GraphView } from "./components/GraphView";
import { PaperList } from "./components/PaperList";
import { Rankings } from "./components/Rankings";
import { RELEVANCE_HELP, ResultsHeader } from "./components/ResultsHeader";
import { SavedSearches } from "./components/SavedSearches";
import { Sidebar } from "./components/Sidebar";
import { SiteFooter } from "./components/SiteFooter";
import { Topbar } from "./components/Topbar";
import { feedOf } from "./feeds";
import {
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
import { loadShowAbstracts, saveShowAbstracts } from "./preferences";
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
import { type CountLine, showsArchive, viewModel } from "./view-model";

const FACET_SIZE = 12;
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
export function App() {
  const { state, query, update, setFilters } = useUrlState();
  const cited = state.view === "cited";
  const rankings = state.view === "rankings";
  const archived = showsArchive(state);
  const {
    categories,
    category,
    storeDays,
    archiveYears,
    archiveRange,
    archiveLeftOut,
    archiveUnranked,
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

  const hasSearchWords = parseQuery(query).text !== "";
  // Rising papers, once two weekly refreshes of the counts are known (CIT-9).
  const gainsSpan = citations.gainsSpan;
  // What this view shows and offers (`view-model.ts`, DEBT-2).
  const model = viewModel(state, { hasSearchWords, gainsKnown: gainsSpan !== null });
  const { triaged, byCount, rising, groupByDay } = model;
  const hiding = triaged && triage.hideSeen && triage.seen.size > 0;
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
  const resultPapers = useMemo(() => results.map(({ paper }) => paper), [results]);
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
  // What the header counts: the saved papers, an archive's years, or the period's papers.
  const count: CountLine | "loading" | null =
    state.view === "reading-list"
      ? { shown: results.length, total: readingList.papers.length, noun: "saved paper" }
      : load.status === "ready" && archived && archiveRange !== null
        ? {
            shown: results.length,
            total: load.index.size,
            noun: `highly cited ${category ?? ""} paper`,
            tail: ` first published ${publishedIn(archiveRange, archiveYears, archiveAsOf)}`,
          }
        : load.status === "ready"
          ? {
              shown: results.length,
              total: load.index.size,
              noun: `${category ?? ""} paper`,
              ...(hiddenCount > 0 && { tail: ` · ${seenHidden(hiddenCount).count}` }),
            }
          : load.status === "loading"
            ? "loading"
            : null;
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
    <Topbar
      view={state.view}
      category={category}
      lastUpdate={lastUpdate}
      readingListSize={readingList.papers.length}
      archiveRange={archiveRange}
      tab={tab}
      theme={theme}
      nextTheme={next}
      onTheme={cycle}
    />
  );

  const footer = <SiteFooter onAbout={() => update({ view: "about" })} />;

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
          <ResultsHeader
            model={model}
            count={count}
            onSort={(sort) => update({ sort })}
            citationsNote={citationsNote}
            gainsSpan={gainsSpan}
            relevanceHelpShown={showRelevanceHelp}
            onRelevanceHelp={() => setShowRelevanceHelp(!showRelevanceHelp)}
            hideSeen={triage.hideSeen}
            onHideSeen={triage.toggleHideSeen}
            showAbstracts={showAbstracts}
            onShowAbstracts={toggleAbstracts}
            papers={resultPapers}
            citations={citations.counts}
            readingList={
              state.view === "reading-list"
                ? {
                    papers: readingList.papers,
                    onImport: (file) =>
                      void readingList.importFile(file, (value) => {
                        const added = savedSearches.importSearches(value);
                        return added
                          ? `${countOf(added, "saved search", "saved searches")} added`
                          : null;
                      }),
                    json: () =>
                      JSON.stringify(
                        readingListFile(readingList.papers, savedSearches.searches),
                        null,
                        2,
                      ),
                  }
                : undefined
            }
          />

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
              {archiveUnranked > 0 &&
                ` The citation counts of ${countOf(archiveUnranked, "year")} could not be loaded: their papers come last.`}
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
              papers={resultPapers}
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
