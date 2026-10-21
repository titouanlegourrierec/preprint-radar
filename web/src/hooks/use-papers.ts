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
import { loadingLine } from "../format";
import {
  lightDays,
  PAPER_BUDGET,
  type Period,
  periodKey,
  periodOfKey,
  selectDays,
} from "../period";
import { PaperIndex } from "../search";
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
 */
export function usePapers(
  requestedCategory: string | null,
  period: Period,
  archive: { years: ArchiveRange | null } | null = null,
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
  // archive's years.
  const loadedPeriod = archived ? null : periodKey(period);

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
  }, [storeIndex, category, loadedPeriod, archiveKey, attempt]);

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
    load,
    /**
     * What a load in progress says ("Loading 3,646 papers of 5 days…"), counted in the
     * index: the days `selectDays` keeps, or the archive's years, as the effect loads them
     * (UX-6).
     */
    loadingLine: loadingLine(
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
    searchable: load.status === "ready" && warmed === load.index ? load.index : null,
    retry: () => setAttempt((count) => count + 1),
    generatedAt: storeIndex?.generated_at ?? null,
  };
}
