import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ALL_YEARS, formatYears, LAST_12_MONTHS, publishedIn } from "./archive-years";
import { About } from "./components/About";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Folders } from "./components/Folders";
import { InfoButton } from "./components/InfoButton";
import { SearchIcon, StarIcon } from "./components/icons";
import { LazyGraphView } from "./components/LazyGraphView";
import { ListNotices, ViewNotes } from "./components/ListNotices";
import { NoResults } from "./components/NoResults";
import { PaperList } from "./components/PaperList";
import { Rankings, RankingsControls } from "./components/Rankings";
import { ResultsHeader } from "./components/ResultsHeader";
import { SavedSearches } from "./components/SavedSearches";
import { Sidebar, SidebarToggle, WIDE_QUERY } from "./components/Sidebar";
import { SiteFooter } from "./components/SiteFooter";
import { Topbar } from "./components/Topbar";
import { feedOf } from "./feeds";
import { findFolder, folderOf } from "./folders";
import {
  countOf,
  citationsNote as formatCitationsNote,
  formatDay,
  gainLabel,
  seenHidden,
  staleCitations,
} from "./format";
import { useCitations } from "./hooks/use-citations";
import { useFolders } from "./hooks/use-folders";
import { useMediaQuery } from "./hooks/use-media-query";
import { usePapers } from "./hooks/use-papers";
import { useReadingList } from "./hooks/use-reading-list";
import { useSavedSearches } from "./hooks/use-saved-searches";
import { useTheme } from "./hooks/use-theme";
import { useTriage } from "./hooks/use-triage";
import { useUrlState } from "./hooks/use-url-state";
import { namedInstitutions } from "./institutions";
import { hasModifier, isTyping } from "./keyboard";
import { between, LONGEST_RANGE, samePeriod, selectDays } from "./period";
import {
  loadShowAbstracts,
  loadSidebarFolded,
  saveShowAbstracts,
  saveSidebarFolded,
} from "./preferences";
import { readingListFile } from "./reading-list";
import { searchOf } from "./saved-searches";
import {
  activeFilterCount,
  alphabetical,
  arxivIdOf,
  byCitations,
  byGains,
  byStars,
  exactly,
  mostlyTied,
  NO_FILTERS,
  nameHighlights,
  parseQuery,
  type SearchResult,
  subjectFacets,
  valueCounts,
} from "./search";
import { searchKey } from "./text";
import type { Paper } from "./types";
import { archiveRangeOf, listKey, paperLink, type ViewState, writeState } from "./url-state";
import { venueFacets } from "./venues";
import { type CountLine, showsArchive, viewModel } from "./view-model";

const VIEW_TITLES: Record<ViewState["view"], string> = {
  papers: "",
  cited: "Highly cited",
  graph: "Graph",
  rankings: "Rankings",
  "reading-list": "Reading list",
  about: "About",
};
const SUGGESTION_SIZE = 300;

/** What the search finds, in the field's ⓘ and for screen readers. */
function SearchHint() {
  return (
    <>
      Searches titles, abstracts, authors, affiliations, venues and comments, or an arXiv id.{" "}
      <code>"neural radiance field"</code> in quotes finds that exact phrase; <code>-survey</code>{" "}
      leaves out the papers that contain the word.
    </>
  );
}

export function App() {
  const { state, query, filters, update, setFilters, correct } = useUrlState();
  const cited = state.view === "cited";
  const rankings = state.view === "rankings";
  const archived = showsArchive(state);
  const {
    categories,
    category,
    storeDays,
    archiveYears,
    topRecent,
    archiveRange,
    archiveLeftOut,
    archiveUnranked,
    missingDays,
    load,
    loadingLine,
    searchable,
    retry,
    generatedAt,
  } = usePapers(state.category, state.period, archived ? { years: state.year } : null);
  // Years the archive does not hold (`?year=2005`) show others, which the URL then names,
  // in place, so that a shared link opens what was seen (SRCH-20).
  const shownYearsKey = archiveRange === null ? null : formatYears(archiveRange);
  useEffect(() => {
    if (!archived || state.year === null || archiveRange === null) return;
    if (formatYears(state.year) !== shownYearsKey) correct({ year: archiveRange });
  }, [archived, state.year, shownYearsKey]);
  const readingList = useReadingList(load.status === "ready" ? load.index : null);
  // The reading list's folders (UX-38): the one the URL names, its papers among the saved.
  const folders = useFolders();
  const activeFolder =
    state.view === "reading-list" ? (findFolder(folders.folders, state.folder) ?? null) : null;
  const folderIds = useMemo(
    () =>
      activeFolder
        ? new Set(activeFolder.papers.filter((id) => readingList.savedIds.has(id)))
        : null,
    [activeFolder, readingList.savedIds],
  );
  // A folder deleted, or one of another browser's link: every saved paper, named so.
  useEffect(() => {
    if (state.view === "reading-list" && state.folder !== null && activeFolder === null) {
      correct({ folder: null });
    }
  }, [state.view, state.folder, activeFolder]);
  // An unsaved paper leaves its folder, which counts the saved ones only.
  const toggleSaved = (paper: Paper) => {
    if (readingList.savedIds.has(paper.arxiv_id)) folders.put(paper.arxiv_id, null);
    readingList.toggle(paper);
  };
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
  // A folded sidebar leaves the papers the whole width (UX-35); phones stack it instead.
  const [sidebarFolded, setSidebarFolded] = useState(loadSidebarFolded);
  const wide = useMediaQuery(WIDE_QUERY);
  const folded = wide && sidebarFolded;

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
  // The stars of the code the papers link, once the weekly refresh gave some (PROD-18).
  const starsKnown = useMemo(
    () => activeIndex?.all().some(({ code }) => code?.stars !== undefined) ?? false,
    [activeIndex],
  );
  // What this view shows and offers (`view-model.ts`, DEBT-2).
  const model = viewModel(state, { hasSearchWords, gainsKnown: gainsSpan !== null, starsKnown });
  const { triaged, byCount, rising, starred, groupByDay } = model;
  const hiding = triaged && triage.hideSeen && triage.seen.size > 0;
  // In three steps, each redone only when what it reads changes (UX-23): marking a paper
  // seen does not search again, nor do late counts when the order ignores them. The index
  // orders by the sort asked (Most cited in Highly cited), so that with search words,
  // equal counts keep the best match first (CIT-6); not by the one pressed, which turns
  // from Most cited to Rising when the gains arrive, an order the index does not tell apart.
  const order = cited ? "citations" : state.sort;
  const found = useMemo(() => {
    if (state.view === "graph") return [];
    const all = activeIndex?.search(query, filters, order) ?? [];
    return folderIds ? all.filter(({ paper }) => folderIds.has(paper.arxiv_id)) : all;
  }, [state.view, activeIndex, query, filters, order, folderIds]);
  const hiddenSeen = hiding ? triage.seen : null;
  // A shared or opened paper stays, seen or not: it is the one asked for.
  const target = state.paper;
  const shown = useMemo(
    () =>
      hiddenSeen
        ? found.filter(({ paper }) => paper.arxiv_id === target || !hiddenSeen.has(paper.arxiv_id))
        : found,
    [found, hiddenSeen, target],
  );
  // Papers that Hide seen leaves out, which the count and an empty list say.
  const hiddenCount = found.length - shown.length;
  const rankingCounts = byCount ? citations.counts : null;
  const rankingGains = state.sort === "rising" ? citations.gains : null;
  // The reading list's own order (UX-39): where each saved paper stands in it.
  const custom = model.custom;
  const savedOrder = useMemo(
    () => new Map(readingList.papers.map((paper, index) => [paper.arxiv_id, index])),
    [readingList.papers],
  );
  const results: SearchResult[] = useMemo(() => {
    if (custom) {
      const at = (result: SearchResult) => savedOrder.get(result.paper.arxiv_id) ?? 0;
      return [...shown].sort((a, b) => at(a) - at(b));
    }
    if (starred) return byStars(shown);
    if (rankingGains && rankingCounts) return byGains(shown, rankingGains, rankingCounts);
    return rankingCounts ? byCitations(shown, rankingCounts) : shown;
  }, [shown, rankingCounts, rankingGains, starred, custom, savedOrder]);
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
  const nameTerms = useMemo(() => nameHighlights(filters), [filters]);
  // The feed of the institution or major venue the papers are filtered on (§17.1 #6).
  const feedInstitution = state.view === "papers" ? filters.affiliation : null;
  const feedKnown = useMemo(() => {
    if (!(feedInstitution?.exact && load.status === "ready")) return false;
    const key = searchKey(feedInstitution.text);
    return load.index
      .all()
      .some((paper) => namedInstitutions(paper).some((name) => searchKey(name) === key));
  }, [feedInstitution, load]);
  const feed =
    state.view === "papers" && category ? feedOf(category, filters, () => feedKnown) : null;
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
  // Where the papers no day file holds are: the archive's years, its last 12 months.
  const storedBefore = {
    oldestDay,
    archiveYears: archiveYears.map((entry) => entry.year),
    recentSince: topRecent?.since,
  };
  const linkTo = (paper: Paper) =>
    paperLink(paper, { ...storedBefore, category: category ?? null });
  // Like venues, over every loaded paper: choosing a subject leaves the others listed.
  const subjects = useMemo(
    () => subjectFacets(activeIndex?.all() ?? [], state.filters.subject, SUGGESTION_SIZE),
    [activeIndex, state.filters.subject],
  );

  const lastUpdate = generatedAt ? formatDay(generatedAt) : null;
  const archiveAsOf = generatedAt ? new Date(generatedAt) : undefined;
  // What the header counts: the saved papers, an archive's years, or the period's papers.
  const count: CountLine | { loading: string } | null =
    state.view === "reading-list"
      ? {
          shown: results.length,
          total: folderIds?.size ?? readingList.papers.length,
          noun: "saved paper",
          ...(activeFolder && { tail: ` in “${activeFolder.name}”` }),
        }
      : load.status === "ready" && archived && archiveRange !== null
        ? {
            shown: results.length,
            total: load.index.size,
            noun: `highly cited ${category ?? ""} paper`,
            tail: ` first published ${publishedIn(archiveRange, archiveYears, archiveAsOf, topRecent)}`,
          }
        : load.status === "ready"
          ? {
              shown: results.length,
              total: load.index.size,
              noun: `${category ?? ""} paper`,
              ...(hiddenCount > 0 && { tail: ` · ${seenHidden(hiddenCount).count}` }),
            }
          : load.status === "loading"
            ? { loading: loadingLine }
            : null;
  // The graph shows the loaded papers; a saved paper from elsewhere brings its day, or
  // its archive year (or the last 12 months) when it is older than the days kept.
  const showInGraph = (paper: Paper) => {
    const loaded = load.status === "ready" && load.index.has(paper.arxiv_id);
    const year = archiveRangeOf(paper.announced, storedBefore);
    if (loaded) {
      update({ view: "graph", paper: paper.arxiv_id, year: archived ? archiveRange : null });
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
  const toggleSidebar = () => {
    setSidebarFolded(!sidebarFolded);
    saveSidebarFolded(!sidebarFolded);
  };
  const toggleAbstracts = () => {
    setShowAbstracts(!showAbstracts);
    saveShowAbstracts(!showAbstracts);
  };

  // Tabs are links, so that they open in a new tab too; a plain click stays in the page.
  // A tab leaves the graph's focus behind (`update` does too): it is the graph's alone.
  const tab = (active: boolean, patch: Partial<ViewState>) => ({
    href: `./${writeState({ ...state, query, filters, paper: null, focus: null, ...patch })}`,
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

  // The top bar spans the window above every view, as the graph's does (UX-32).
  if (state.view === "about") {
    return (
      <>
        {skipLink}
        {topbar}
        <div class="layout">
          {/* A view that fails to draw leaves the tabs usable (TEST-10). */}
          <ErrorBoundary what="this view">
            <About />
          </ErrorBoundary>
          {footer}
        </div>
      </>
    );
  }

  if (state.view === "graph") {
    return (
      <div class="layout layout--graph">
        {skipLink}
        {topbar}
        <ErrorBoundary what="the graph" resetKeys={[state, load]}>
          <LazyGraphView
            papers={graphPapers}
            citations={citations.counts}
            citationsNote={citationsNote}
            focus={state.focus}
            onFocus={(focus) => update({ focus })}
            notice={
              load.status === "loading"
                ? { loading: loadingLine }
                : load.status === "error"
                  ? { error: load.message, onRetry: retry }
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
            topRecent={topRecent}
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
        </ErrorBoundary>
      </div>
    );
  }

  return (
    <>
      {skipLink}
      {topbar}
      <div class="layout">
        {/* The search as the graph's Find field (UX-33): its icon, its key, and its syntax
            and the list's keys behind an ⓘ. */}
        <div class="search">
          <div class="search__field">
            <SearchIcon />
            <input
              type="search"
              class="search__input"
              ref={searchInput}
              placeholder="Search papers…"
              value={state.query}
              onInput={(event) => update({ query: event.currentTarget.value })}
              aria-label="Search papers"
              aria-describedby="search-hint"
              aria-keyshortcuts="/"
              // No autofocus: j and k would type into the box. "/" comes here, Escape leaves.
              onKeyDown={(event) => {
                if (event.key !== "Escape") return;
                // Leave the box, keeping its words (a search box clears them on Escape).
                event.preventDefault();
                event.currentTarget.blur();
              }}
            />
            {state.query === "" && (
              <span class="search__key" aria-hidden="true">
                /
              </span>
            )}
            <InfoButton label="Search syntax and keys" class="search__info" end>
              <p>
                <SearchHint />
              </p>
              {triaged && (
                <p class="search__keys">
                  Keys: <kbd>j</kbd> <kbd>k</kbd> move, <kbd>o</kbd> open, <kbd>s</kbd> save,{" "}
                  <kbd>x</kbd> seen, <kbd>/</kbd> search, <kbd>Esc</kbd> leave the search.
                </p>
              )}
              {state.view === "reading-list" && (
                <p class="search__keys">
                  Keys: <kbd>j</kbd> <kbd>k</kbd> move, <kbd>o</kbd> open, <kbd>s</kbd> remove,{" "}
                  <kbd>Alt</kbd> <kbd>↑</kbd> <kbd>↓</kbd> move a paper in My order.
                </p>
              )}
            </InfoButton>
          </div>
        </div>
        {/* The syntax said to screen readers in the field, whose ⓘ shows it (UX-33). */}
        <p id="search-hint" class="visually-hidden">
          <SearchHint />
        </p>

        <div class={folded ? "content content--folded" : "content"}>
          {category && (
            <Sidebar
              folders={
                state.view === "reading-list" && (
                  <Folders
                    folders={folders.folders}
                    savedIds={readingList.savedIds}
                    active={activeFolder?.name ?? null}
                    onSelect={(folder) => update({ folder })}
                    onAdd={folders.add}
                    onRename={(from, to) => {
                      const renamed = folders.rename(from, to);
                      if (renamed && activeFolder?.name === from) update({ folder: renamed });
                    }}
                    onDelete={(name) => {
                      folders.remove(name);
                      update({ folder: null });
                    }}
                    onDropPaper={(name, arxivId) => folders.put(arxivId, name)}
                  />
                )
              }
              categories={categories}
              category={category}
              asOf={archiveAsOf}
              recent={topRecent}
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
                cited || rankings
                  ? {
                      years: archiveYears,
                      range: cited ? (archiveRange ?? ALL_YEARS) : archived ? archiveRange : null,
                      onRange: (year) => update({ year }),
                      only: cited,
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
                  current={{ query, filters }}
                  onSave={() => savedSearches.save({ query, filters })}
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
            {/* A list that fails to draw leaves the tabs and the sidebar usable (TEST-10), and
              another period, filter or Back draws it again. */}
            <ErrorBoundary key={state.view} what="this view" resetKeys={[state, load]}>
              <ResultsHeader
                model={model}
                count={count}
                onSort={(sort) => update({ sort })}
                citationsNote={citationsNote}
                gainsSpan={gainsSpan}
                sidebarToggle={
                  wide &&
                  category && (
                    <SidebarToggle
                      folded={folded}
                      active={activeFilterCount(state.filters)}
                      onToggle={toggleSidebar}
                    />
                  )
                }
                notes={
                  <ViewNotes
                    view={state.view}
                    papers={resultPapers}
                    citationsNote={citationsNote}
                    archived={archived}
                    lastMonths={archived && archiveRange === LAST_12_MONTHS}
                  />
                }
                controls={
                  rankings && (
                    <RankingsControls
                      archived={archived}
                      kind={state.rank}
                      metric={state.metric}
                      onKind={(rank) => update({ rank })}
                      onMetric={(metric) => update({ metric })}
                    />
                  )
                }
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
                            const searches = added
                              ? `${countOf(added, "saved search", "saved searches")} added`
                              : null;
                            const filed = folders.importFolders(value);
                            return [searches, filed].filter(Boolean).join("; ") || null;
                          }),
                        json: () =>
                          JSON.stringify(
                            readingListFile(
                              readingList.papers,
                              savedSearches.searches,
                              folders.folders,
                            ),
                            null,
                            2,
                          ),
                      }
                    : undefined
                }
              />

              <ListNotices
                readingListMessage={
                  state.view === "reading-list" && readingList.message
                    ? { text: readingList.message, onDismiss: readingList.dismissMessage }
                    : null
                }
                sinceLastVisit={
                  triaged && sinceLastVisit && !samePeriod(state.period, sinceLastVisit.period)
                    ? {
                        papers: sinceLastVisit.papers,
                        onShow: () => update({ period: sinceLastVisit.period }),
                      }
                    : null
                }
                missingDays={
                  missingDays.length > 0 && load.status === "ready"
                    ? { days: missingDays, onRetry: retry }
                    : null
                }
                archiveBudget={
                  archiveLeftOut > 0 && load.status === "ready"
                    ? { shown: load.index.size, leftOut: archiveLeftOut, unranked: archiveUnranked }
                    : null
                }
                staleCitations={
                  citationsNote && citations.asOf && staleCitations(citations.asOf)
                    ? citationsNote
                    : null
                }
                mostlyTied={
                  byCount && !rising && !rankings && mostlyTied(results, citations.counts)
                }
                filters={rankings ? null : state.filters}
                onFilters={setFilters}
                feed={feed}
              />

              {load.status === "error" && state.view !== "reading-list" ? (
                <p class="notice notice--error" role="alert">
                  Could not load the papers: {load.message}.{" "}
                  <button type="button" class="link-button" onClick={retry}>
                    Retry
                  </button>
                </p>
              ) : rankings && load.status === "ready" ? (
                <Rankings
                  papers={resultPapers}
                  citations={citations.counts}
                  citationsNote={citationsNote}
                  archived={archived}
                  kind={state.rank}
                  metric={state.metric}
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
              ) : cited && archiveYears.length === 0 && !topRecent ? (
                <p class="notice">
                  The archive of highly cited papers is built weekly, from citation counts: it is
                  not there yet.
                </p>
              ) : state.view === "reading-list" && readingList.papers.length === 0 ? (
                <p class="notice">
                  Your reading list is empty. Use <StarIcon />
                  <span class="visually-hidden">the star</span> on a paper to save it; the list is
                  kept in this browser.
                </p>
              ) : activeFolder && folderIds?.size === 0 ? (
                <p class="notice">
                  No paper in “{activeFolder.name}” yet: choose this folder in the folder menu of a
                  saved paper's card.
                </p>
              ) : (
                <>
                  <NoResults
                    missingPaper={
                      (state.view === "papers" || cited) &&
                      state.paper &&
                      load.status === "ready" &&
                      !load.index.has(state.paper)
                        ? state.paper
                        : null
                    }
                    missingFromCited={cited}
                    missingPastedId={
                      pastedId &&
                      results.length === 0 &&
                      hiddenCount === 0 &&
                      load.status === "ready"
                        ? pastedId
                        : null
                    }
                    allSeen={results.length === 0 ? hiddenCount : 0}
                    onShowSeen={triage.toggleHideSeen}
                    noMatch={
                      !pastedId &&
                      results.length === 0 &&
                      hiddenCount === 0 &&
                      (load.status === "ready" || state.view === "reading-list") &&
                      activeIndex !== null &&
                      activeIndex.size > 0
                        ? {
                            inPeriod: state.view === "papers",
                            onClearFilters:
                              activeFilterCount(state.filters) > 0
                                ? () => setFilters(NO_FILTERS)
                                : null,
                            wider:
                              state.view === "papers" && widerPeriod
                                ? {
                                    days: longestDays,
                                    onSearch: () => update({ period: longestPeriod }),
                                  }
                                : null,
                          }
                        : null
                    }
                  />
                  <PaperList
                    results={results}
                    resetKey={listKey({ ...state, filters }, query)}
                    nameHighlights={nameTerms}
                    groupByDay={groupByDay}
                    ranked={model.ranked}
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
                    onToggleSaved={toggleSaved}
                    seenIds={triaged ? triage.seen : undefined}
                    onToggleSeen={triaged ? triage.toggleSeen : undefined}
                    onAuthor={(author) => setFilters({ ...state.filters, author: exactly(author) })}
                    onAffiliation={(affiliation) => setFilters({ ...state.filters, affiliation })}
                    onMove={custom ? readingList.move : undefined}
                    folders={
                      state.view === "reading-list"
                        ? {
                            names: folders.folders.map((folder) => folder.name),
                            of: (arxivId) => folderOf(folders.folders, arxivId),
                            onPut: folders.put,
                          }
                        : undefined
                    }
                  />
                </>
              )}
            </ErrorBoundary>
          </main>
        </div>

        {footer}
      </div>
    </>
  );
}
