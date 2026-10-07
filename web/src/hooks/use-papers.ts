import { useEffect, useState } from "preact/hooks";
import { formatYears, parseYears, shownYears, type YearRange, yearsIn } from "../archive-years";
import { loadArchiveYears, loadDays, loadIndex } from "../data";
import { PAPER_BUDGET, type Period, selectDays } from "../period";
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
  // Papers of the archive's years left out by the budget.
  const [leftOut, setLeftOut] = useState(0);
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

  useEffect(() => {
    if (!storeIndex) return;
    if (!category) {
      setLoad({ status: "error", message: "The data store is empty." });
      return;
    }
    // Another period, year or category: the requests left and the indexing stop.
    const stop = new AbortController();
    const { signal } = stop;
    setLoad({ status: "loading" });
    let loaded: Promise<{ papers: Paper[]; total: number }>;
    const range = parseYears(archiveKey);
    if (!archived) {
      const days = selectDays(storeIndex.categories[category] ?? [], period);
      loaded = loadDays(category, days, signal).then((papers) => ({
        papers,
        total: papers.length,
      }));
    } else if (range === null) {
      loaded = Promise.resolve({ papers: [], total: 0 }); // no archive yet
    } else {
      const years = yearsIn(range, storeIndex.archives?.[category] ?? []).map(({ year }) => year);
      loaded = loadArchiveYears(category, years, PAPER_BUDGET, signal);
    }
    loaded
      .then(({ papers, total }) => {
        if (signal.aborted) return;
        setLeftOut(total - papers.length);
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
  }, [storeIndex, category, period, archived, archiveKey, attempt]);

  return {
    categories,
    category,
    storeDays,
    archiveYears,
    /** The archive's years shown, `null` for the recent days or before the first archive. */
    archiveRange,
    /** Papers of those years left out by the budget, the least cited for their age. */
    archiveLeftOut: archived ? leftOut : 0,
    load,
    /** The papers loaded, once a search over them costs no indexing; else `null`. */
    searchable: load.status === "ready" && warmed === load.index ? load.index : null,
    retry: () => setAttempt((count) => count + 1),
    generatedAt: storeIndex?.generated_at ?? null,
  };
}
