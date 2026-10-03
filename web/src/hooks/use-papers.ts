import { useEffect, useState } from "preact/hooks";
import { loadArchive, loadDays, loadIndex } from "../data";
import { type Period, selectDays } from "../period";
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
 * With `archive` set, the papers are those of one year of the archive of highly cited
 * older papers instead: the requested year, else the latest one.
 */
export function usePapers(
  requestedCategory: string | null,
  period: Period,
  archive: { year: number | null } | null = null,
) {
  const [storeIndex, setStoreIndex] = useState<StoreIndex | null>(null);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
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
  const archiveYear = archive
    ? ((archiveYears.find(({ year }) => year === archive.year) ?? archiveYears[0])?.year ?? null)
    : null;
  const archived = archive !== null;

  useEffect(() => {
    if (!storeIndex) return;
    if (!category) {
      setLoad({ status: "error", message: "The data store is empty." });
      return;
    }
    let cancelled = false;
    setLoad({ status: "loading" });
    let papers: Promise<Paper[]>;
    if (!archived) {
      papers = loadDays(category, selectDays(storeIndex.categories[category] ?? [], period));
    } else if (archiveYear === null) {
      papers = Promise.resolve([]); // no archive yet
    } else {
      papers = loadArchive(category, archiveYear);
    }
    papers
      .then((papers) => !cancelled && setLoad({ status: "ready", index: new PaperIndex(papers) }))
      .catch(
        (error: unknown) =>
          !cancelled && setLoad({ status: "error", message: loadErrorMessage(error) }),
      );
    return () => {
      cancelled = true;
    };
  }, [storeIndex, category, period, archived, archiveYear, attempt]);

  return {
    categories,
    category,
    storeDays,
    archiveYears,
    archiveYear,
    load,
    retry: () => setAttempt((count) => count + 1),
    generatedAt: storeIndex?.generated_at ?? null,
  };
}
