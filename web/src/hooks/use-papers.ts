import { useEffect, useState } from "preact/hooks";
import { formatYears, parseYears, shownYears, type YearRange, yearsIn } from "../archive-years";
import { loadArchiveYears, loadDays, loadIndex } from "../data";
import { loadingLine } from "../format";
import { PAPER_BUDGET, type Period, periodKey, periodOfKey, selectDays } from "../period";
import { PaperIndex } from "../search";
import type { ArchiveSummary, DaySummary, Paper, StoreIndex } from "../types";

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
 * archive's own score, from the citation shards of those years.
 */
export function usePapers(
  requestedCategory: string | null,
  period: Period,
  archive: { years: YearRange | null } | null = null,
) {
  const [storeIndex, setStoreIndex] = useState<StoreIndex | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  // The loaded index once its full-text index is built, for searches that can wait for it.
  const [warmed, setWarmed] = useState<PaperIndex | null>(null);
  // Papers of the archive's years left out by the budget, and years it could not rank.
  const [leftOut, setLeftOut] = useState({ papers: 0, unranked: 0 });
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
  const archiveRange = archive ? shownYears(archive.years, archiveYears) : null;
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
    let loaded: Promise<{ papers: Paper[]; total: number; unranked: number }>;
    const range = parseYears(archiveKey);
    if (loadedPeriod !== null) {
      const days = selectDays(storeIndex.categories[category] ?? [], periodOfKey(loadedPeriod));
      loaded = loadDays(category, days, signal).then((papers) => ({
        papers,
        total: papers.length,
        unranked: 0,
      }));
    } else if (range === null) {
      loaded = Promise.resolve({ papers: [], total: 0, unranked: 0 }); // no archive yet
    } else {
      const years = yearsIn(range, storeIndex.archives?.[category] ?? []).map(({ year }) => year);
      loaded = loadArchiveYears(category, years, PAPER_BUDGET, signal);
    }
    loaded
      .then(({ papers, total, unranked }) => {
        if (signal.aborted) return;
        setLeftOut({ papers: total - papers.length, unranked });
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
    /** The archive's years shown, `null` for the recent days or before the first archive. */
    archiveRange,
    /** Papers of those years left out by the budget, the least cited for their age. */
    archiveLeftOut: archived ? leftOut.papers : 0,
    /** Years of those whose citation counts did not load: their papers ranked last. */
    archiveUnranked: archived ? leftOut.unranked : 0,
    load,
    /**
     * What a load in progress says ("Loading 3,646 papers of 5 days…"), counted in the
     * index: the days `selectDays` keeps, or the archive's years, as the effect loads them
     * (UX-6).
     */
    loadingLine: loadingLine(
      archived
        ? { years: archiveRange === null ? [] : yearsIn(archiveRange, archiveYears) }
        : { days: selectDays(storeDays, period) },
    ),
    /** The papers loaded, once a search over them costs no indexing; else `null`. */
    searchable: load.status === "ready" && warmed === load.index ? load.index : null,
    retry: () => setAttempt((count) => count + 1),
    generatedAt: storeIndex?.generated_at ?? null,
  };
}
