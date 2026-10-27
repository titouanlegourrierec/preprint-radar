import { useEffect, useState } from "preact/hooks";
import {
  type ArchiveRange,
  formatYears,
  LAST_12_MONTHS,
  parseYears,
  shownYears,
  yearsIn,
} from "../archive-years";
import { loadArchiveYears, loadDays, loadIndex, loadLightDays, loadTopRecent } from "../data";
import { loadingLine, storeSearchLine } from "../format";
import {
  lightDays,
  PAPER_BUDGET,
  type Period,
  periodKey,
  periodOfKey,
  selectDays,
} from "../period";
import { PaperIndex, type SearchFilters } from "../search";
import type { StoreProgress, StoreSearch } from "../store-search";
import type { ArchiveSummary, DaySummary, Paper, StoreIndex, TopRecentSummary } from "../types";

/**
 * What a failed load means for a reader: "TypeError: Failed to fetch" says the network or
 * the site did not answer.
 */
export function loadErrorMessage(error: unknown): string {
  if (error instanceof TypeError) return "the network or the site did not answer";
  return error instanceof Error ? error.message : String(error);
}

/** Run `task` once the browser is idle (Safari has no `requestIdleCallback`). */
function whenIdle(task: () => void): void {
  if ("requestIdleCallback" in window) window.requestIdleCallback(task);
  else setTimeout(task, 50);
}

/**
 * Least time a search of every stored paper's line stays (UX-51): files come twenty a
 * second, faster than a line is read.
 */
const STORE_LINE_MS = 500;

export type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: PaperIndex };

/**
 * The papers of one category over a period, loaded from the store and indexed for search.
 *
 * The requested category falls back to the first one in the store when it is unknown
 * (e.g. an old link after a category was dropped).
 *
 * With `archive` set, the papers are those of years of the archive of highly cited older
 * papers instead: the requested ones, else the latest year. Over {@link PAPER_BUDGET}
 * papers (all years hold 22,000), the best ranked by citations per year of age, the
 * archive's own score, from the citation shards of those years. Or the most cited papers
 * of the last 12 months, once the archive keeps them (PROD-11).
 *
 * With `everywhere` set, the papers are those of the whole store that its words and filters
 * find (PROD-21): every day file, the most cited papers of the last 12 months and the
 * archive's years, read one after the other (`searchStore`), the period aside. None
 * without a word or a filter, which would find them all.
 */
export function usePapers(
  requestedCategory: string | null,
  period: Period,
  archive: { years: ArchiveRange | null } | null = null,
  everywhere: { query: string; filters: SearchFilters } | null = null,
) {
  const [storeIndex, setStoreIndex] = useState<StoreIndex | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  // The loaded index once its full-text index is built, for searches that can wait for it.
  const [warmed, setWarmed] = useState<PaperIndex | null>(null);
  // Papers of the archive's years left out by the budget, and years it could not rank.
  const [leftOut, setLeftOut] = useState({ papers: 0, unranked: 0 });
  // Days of the period whose day file or search shard did not load, not shown (SRCH-10).
  const [missingDays, setMissingDays] = useState<string[]>([]);
  // Each Retry loads again what failed: the index, or the papers.
  const [attempt, setAttempt] = useState(0);
  // A search of every stored paper: how far it went, then the papers it found, ranked.
  const [scan, setScan] = useState<StoreProgress | { ranking: number }>({ read: 0, found: 0 });
  // The words and filters it is of: the last search's, until another's effect starts it.
  const [scanned, setScanned] = useState<string | null>(null);
  // What it found, once done; `null` without a word nor a filter to search for.
  const [storeSearch, setStoreSearch] = useState<Omit<StoreSearch, "papers"> | null>(null);
  // What the index holds the papers of (`wanted` then): their category, period, years or
  // search, which another must not show nor search, even for a frame.
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  useEffect(() => {
    if (attempt > 0 && storeIndex) return;
    setLoad({ status: "loading" });
    loadIndex()
      .then(setStoreIndex)
      .catch((error: unknown) => setLoad({ status: "error", message: loadErrorMessage(error) }));
  }, [attempt]);

  const categories = storeIndex ? Object.keys(storeIndex.categories).sort() : [];
  const category =
    requestedCategory && categories.includes(requestedCategory) ? requestedCategory : categories[0];
  const storeDays: DaySummary[] = (category && storeIndex?.categories[category]) || [];
  const archiveYears: ArchiveSummary[] = (category && storeIndex?.archives?.[category]) || [];
  const topRecent: TopRecentSummary | undefined =
    (category && storeIndex?.top_recent?.[category]) || undefined;
  const archiveRange = archive ? shownYears(archive.years, archiveYears, topRecent) : null;
  // A key for the effect: the range is a new object at each render.
  const archiveKey = archiveRange === null ? null : formatYears(archiveRange);
  const archived = archive !== null;
  // Keys for the effect, equal for equal periods and ranges: another object for the same
  // period (Back, a preset chosen again) loads nothing again, nor does a period behind the
  // archive's years or a search of every paper, whose words and filters are its own key.
  const searchedKey = everywhere && !archived ? JSON.stringify(everywhere) : null;
  const loadedPeriod = archived || searchedKey !== null ? null : periodKey(period);
  const wanted = JSON.stringify([category ?? null, loadedPeriod, archiveKey, searchedKey]);

  useEffect(() => {
    if (!storeIndex) return;
    if (!category) {
      setLoad({ status: "error", message: "The data store is empty" });
      return;
    }
    // Another period, year or category: the requests left and the indexing stop.
    const stop = new AbortController();
    const { signal } = stop;
    setLoad({ status: "loading" });
    // The former index and its full-text index can go: two would hold 20,000 papers.
    setWarmed(null);
    setLoadedFor(null);
    if (searchedKey !== null) {
      const { query, filters } = JSON.parse(searchedKey) as {
        query: string;
        filters: SearchFilters;
      };
      searchEverything(category, storeIndex, query, filters, signal, searchedKey, wanted);
      return () => stop.abort();
    }
    let loaded: Promise<{ papers: Paper[]; total: number; unranked: number; missing?: string[] }>;
    const range = parseYears(archiveKey);
    if (loadedPeriod !== null) {
      // The latest days whole, the older ones from the search shards (PERF-1).
      const period = periodOfKey(loadedPeriod);
      const known = storeIndex.categories[category] ?? [];
      const older = lightDays(known, period);
      loaded = Promise.all([
        loadDays(category, selectDays(known, period), signal),
        older.length > 0 ? loadLightDays(category, older) : { papers: [], missing: [] },
      ]).then(([whole, light]) => ({
        papers: [...light.papers, ...whole.papers],
        total: light.papers.length + whole.papers.length,
        unranked: 0,
        missing: [...whole.missing, ...light.missing],
      }));
    } else if (range === null) {
      loaded = Promise.resolve({ papers: [], total: 0, unranked: 0 }); // no archive yet
    } else if (range === LAST_12_MONTHS) {
      loaded = loadTopRecent(category, signal).then((papers) => ({
        papers,
        total: papers.length,
        unranked: 0,
      }));
    } else {
      const years = yearsIn(range, storeIndex.archives?.[category] ?? []).map(({ year }) => year);
      loaded = loadArchiveYears(category, years, PAPER_BUDGET, signal);
    }
    loaded
      .then(({ papers, total, unranked, missing = [] }) => {
        if (signal.aborted) return;
        setLeftOut({ papers: total - papers.length, unranked });
        setMissingDays(missing);
        const index = new PaperIndex(papers);
        setLoad({ status: "ready", index });
        setLoadedFor(wanted);
        // The list shows first; the search index is built after, while the page is idle.
        whenIdle(() => {
          index.warm(signal).then(() => !signal.aborted && setWarmed(index));
        });
      })
      .catch(
        (error: unknown) =>
          !signal.aborted && setLoad({ status: "error", message: loadErrorMessage(error) }),
      );
    return () => stop.abort();
  }, [storeIndex, category, loadedPeriod, archiveKey, searchedKey, attempt]);

  /**
   * Every stored paper through the words and filters' test, then the index of those that
   * pass, built while the page stays responsive, which the list searches as a period's.
   */
  function searchEverything(
    category: string,
    storeIndex: StoreIndex,
    query: string,
    filters: SearchFilters,
    signal: AbortSignal,
    key: string,
    loaded: string,
  ): void {
    setScan({ read: 0, found: 0 });
    setScanned(key);
    setStoreSearch(null);
    setMissingDays([]);
    const holding = {
      days: storeIndex.categories[category] ?? [],
      archiveYears: (storeIndex.archives?.[category] ?? []).map(({ year }) => year),
      topRecent: storeIndex.top_recent?.[category] !== undefined,
    };
    // The search's code too comes with its first use (PERF-15).
    import("../store-search")
      .then(async ({ candidateTest, searchStore }) => {
        const test = candidateTest(query, filters);
        if (signal.aborted) return;
        if (test === null) {
          const index = new PaperIndex([]);
          setLoad({ status: "ready", index });
          setWarmed(index);
          setLoadedFor(loaded);
          return;
        }
        let toldAt = performance.now();
        const onRead = (progress: StoreProgress) => {
          if (signal.aborted || performance.now() - toldAt < STORE_LINE_MS) return;
          toldAt = performance.now();
          setScan(progress);
        };
        const { papers, ...found } = await searchStore(category, holding, test, onRead, signal);
        if (signal.aborted) return;
        setScan({ ranking: papers.length });
        // The few the test let through that the index does not match, it leaves out.
        const index = new PaperIndex(papers);
        await index.warm(signal);
        if (signal.aborted) return;
        setStoreSearch(found);
        setMissingDays(found.missing.days);
        setLoad({ status: "ready", index });
        setWarmed(index);
        setLoadedFor(loaded);
      })
      .catch(
        (error: unknown) =>
          !signal.aborted && setLoad({ status: "error", message: loadErrorMessage(error) }),
      );
  }

  // The papers a search of every stored paper reads, for its progress.
  const storedPapers =
    storeDays.reduce((sum, { count }) => sum + count, 0) +
    (topRecent?.count ?? 0) +
    archiveYears.reduce((sum, { count }) => sum + count, 0);

  // Another category, period, years, words or filters: the papers of the last ones until
  // its effect starts loading (a view's first render), which must not show, even ranked
  // in another view for a frame, nor be searched with other words.
  const shown: LoadState =
    load.status === "ready" && loadedFor !== wanted ? { status: "loading" } : load;

  return {
    categories,
    category,
    storeDays,
    archiveYears,
    /** The category's papers of each complete year, as their citations rank them (decision 22). */
    cohorts: (category && storeIndex?.cohorts?.[category]) || undefined,
    /** The most cited papers of the last 12 months, once the archive keeps them. */
    topRecent,
    /**
     * The archive's years shown, or its last 12 months; `null` for the recent days or before
     * the first archive.
     */
    archiveRange,
    /** Papers of those years left out by the budget, the least cited for their age. */
    archiveLeftOut: archived ? leftOut.papers : 0,
    /** Years of those whose citation counts did not load: their papers ranked last. */
    archiveUnranked: archived ? leftOut.unranked : 0,
    /** Days of the period whose papers did not load ("2026-09-25"), not shown. */
    missingDays: archived ? [] : missingDays,
    /**
     * A search of every stored paper, once done (PROD-21): the papers it read, those it
     * left out past the budget, the archive's files it could not load; `null` while it
     * runs, outside one, or without a word nor a filter to search for.
     */
    storeSearch: searchedKey !== null && shown.status === "ready" ? storeSearch : null,
    load: shown,
    /**
     * What a load in progress says ("Loading 3,646 papers of 5 days…"), counted in the
     * index: the days `selectDays` keeps, or the archive's years, as the effect loads them
     * (UX-6).
     */
    loadingLine:
      searchedKey !== null
        ? storeSearchLine(scanned === searchedKey ? scan : { read: 0, found: 0 }, storedPapers)
        : loadingLine(
            archived
              ? archiveRange === LAST_12_MONTHS && topRecent
                ? { recent: topRecent }
                : {
                    years:
                      archiveRange === null || archiveRange === LAST_12_MONTHS
                        ? []
                        : yearsIn(archiveRange, archiveYears),
                  }
              : { days: [...selectDays(storeDays, period), ...lightDays(storeDays, period)] },
          ),
    /** The papers loaded, once a search over them costs no indexing; else `null`. */
    searchable: shown.status === "ready" && warmed === shown.index ? shown.index : null,
    retry: () => setAttempt((count) => count + 1),
    generatedAt: storeIndex?.generated_at ?? null,
  };
}
